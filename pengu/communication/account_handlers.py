#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Account Switcher message handlers
Mixed into MessageHandler; kept separate so the account code stays in a small file.
"""

import json
import logging

log = logging.getLogger(__name__)


class AccountHandlersMixin:
    """Account Switcher handlers. Needs self._send_response(message: str) from MessageHandler."""

    def _route_account_message(self, payload_type: str, payload: dict) -> bool:
        """Handle an account-* message. Returns False if the type isn't an account message."""
        routes = {
            "account-list": self._handle_account_list,
            "account-switch": self._handle_account_switch,
            "account-remove": self._handle_account_remove,
            "account-open-manager": self._handle_account_open_manager,
        }
        handler = routes.get(payload_type)
        if handler is None:
            return False
        handler(payload)
        return True

    def _get_account_manager(self):
        """Get or create the global account manager instance."""
        from main.account_manager import get_account_manager
        return get_account_manager()

    def _send_account_response(self, request: dict, payload: dict) -> None:
        """Send a response back to the plugin via WebSocket."""
        payload['requestId'] = request.get('requestId')
        self._send_response(json.dumps(payload))

    def _handle_account_list(self, payload: dict) -> None:
        """Return list of all saved accounts."""
        try:
            account_manager = self._get_account_manager()
            accounts = account_manager.get_all_accounts()
            active = account_manager.get_active_account()

            # Never send the login username or password to the League client
            result = []
            for acc in accounts:
                result.append({
                    "id": acc.id,
                    "riotId": acc.riot_id,  # "" until Rose has seen this account signed in
                    "region": acc.region,
                    "tier": acc.tier,
                    "division": acc.division,
                    "lp": acc.lp,
                    "level": acc.level,
                    "note": acc.note,
                    "isActive": bool(active and acc.id == active.id),
                })

            response = {
                "type": "account-list-response",
                "accounts": result,
                "activeAccountId": active.id if active else None,
            }
            self._send_account_response(payload, response)
        except Exception as e:
            log.error(f"[AccountSwitcher] Failed to list accounts: {e}")
            self._send_account_response(payload, {"type": "account-list-response", "accounts": [], "error": str(e)})

    def _handle_account_switch(self, payload: dict) -> None:
        """Start signing the Riot Client in to a saved account (League closes and restarts)."""
        try:
            account_id = payload.get("id", "")
            if not account_id:
                self._send_account_response(payload, {"type": "account-switch-response", "success": False, "error": "Account id is required"})
                return
            if not self._get_account_manager().get_account(account_id):
                self._send_account_response(payload, {"type": "account-switch-response", "success": False, "error": "Account not found"})
                return

            from main.account_secrets import get_password
            if not get_password(account_id):
                self._send_account_response(payload, {"type": "account-switch-response", "success": False, "error": "No saved password for this account. Add it in Rose's account window (Edit)."})
                return

            from main.account_login import game_in_progress, switch_in_background
            if game_in_progress():
                self._send_account_response(payload, {"type": "account-switch-response", "success": False, "error": "Can't switch accounts during a game"})
                return

            # Reply first: the switch closes this League client, and with it the panel
            self._send_account_response(payload, {"type": "account-switch-response", "success": True, "id": account_id})
            switch_in_background(account_id)
        except Exception as e:
            log.error(f"[AccountSwitcher] Failed to switch account: {e}")
            self._send_account_response(payload, {"type": "account-switch-response", "success": False, "error": str(e)})

    def _handle_account_remove(self, payload: dict) -> None:
        """Remove an account."""
        try:
            account_id = payload.get("id", "")
            if not account_id:
                self._send_account_response(payload, {"type": "account-remove-response", "success": False, "error": "Account id is required"})
                return

            success = self._get_account_manager().remove_account(account_id)
            response = {"type": "account-remove-response", "success": success, "id": account_id}
            if not success:
                response["error"] = "Account not found"
            self._send_account_response(payload, response)
        except Exception as e:
            log.error(f"[AccountSwitcher] Failed to remove account: {e}")
            self._send_account_response(payload, {"type": "account-remove-response", "success": False, "error": str(e)})

    def _handle_account_open_manager(self, payload: dict) -> None:
        """Open Rose's Account Switcher window, the same way the tray menu item does."""
        try:
            from main.account_gui import open_account_switcher_thread

            open_account_switcher_thread()
            self._send_account_response(payload, {"type": "account-open-manager-response", "success": True})
        except Exception as e:
            log.error(f"[AccountSwitcher] Failed to open account manager: {e}")
            self._send_account_response(payload, {"type": "account-open-manager-response", "success": False, "error": str(e)})

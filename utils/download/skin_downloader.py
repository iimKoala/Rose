#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skin Downloader
Automatically downloads skins from the GitHub repository
"""

import requests
from pathlib import Path
from typing import Callable, List, Dict, Optional
from utils.core.logging import get_logger
from utils.core.paths import get_skins_dir
from config import (
    APP_USER_AGENT,
    DEFAULT_SKIN_DOWNLOAD_TIMEOUT_S, SKIN_DOWNLOAD_STREAM_TIMEOUT_S
)

log = get_logger()

ProgressCallback = Callable[[int, Optional[str]], None]


class SkinDownloader:
    """Downloads skins from the GitHub repository"""
    
    def __init__(self, target_dir: Path = None, repo_url: str = "https://github.com/darkseal-org/lol-skins"):
        self.repo_url = repo_url
        self.api_base = "https://api.github.com/repos/darkseal-org/lol-skins"
        # Use user data directory for skins to avoid permission issues
        self.target_dir = target_dir or get_skins_dir()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': APP_USER_AGENT,
            'Accept': 'application/vnd.github.v3+json'
        })
        
    def get_repo_contents(self, path: str = "skins") -> List[Dict]:
        """Get the contents of a directory from the GitHub repository"""
        url = f"{self.api_base}/contents/{path}"
        
        try:
            response = self.session.get(url, timeout=DEFAULT_SKIN_DOWNLOAD_TIMEOUT_S)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Failed to fetch repository contents: {e}")
            return []
    
    def download_file(self, download_url: str, local_path: Path) -> bool:
        """Download a file from GitHub"""
        try:
            response = self.session.get(download_url, timeout=SKIN_DOWNLOAD_STREAM_TIMEOUT_S, stream=True)
            response.raise_for_status()
            
            # Create directory if it doesn't exist
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return True
        except requests.RequestException as e:
            log.error(f"Failed to download {download_url}: {e}")
            return False
        except Exception as e:
            log.error(f"Error saving file {local_path}: {e}")
            return False
    
    def get_detailed_stats(self) -> Dict[str, int]:
        """
        Get detailed statistics categorizing base skins and chromas
        
        Structure:
        - Base skin: Champion/Skin Name.zip
        - Chroma: Champion/chromas/Skin Name/Skin Name CHROMAID.zip
        
        Returns:
            Dict with keys: 'total_skins', 'total_chromas', 'total_ids'
        """
        if not self.target_dir.exists():
            return {'total_skins': 0, 'total_chromas': 0, 'total_ids': 0}
        
        total_skins = 0  # Base skins only
        total_chromas = 0  # Chromas only
        
        for champion_dir in self.target_dir.iterdir():
            if not champion_dir.is_dir():
                continue
            
            # Count base skins (skin archives in champion root)
            base_skins = list(champion_dir.glob("*.zip")) + list(champion_dir.glob("*.fantome"))
            total_skins += len(base_skins)

            # Count chromas (skin archives in chromas/*/ subdirectories)
            chromas_dir = champion_dir / "chromas"
            if chromas_dir.exists() and chromas_dir.is_dir():
                for skin_chroma_dir in chromas_dir.iterdir():
                    if skin_chroma_dir.is_dir():
                        chroma_files = list(skin_chroma_dir.glob("*.zip")) + list(skin_chroma_dir.glob("*.fantome"))
                        total_chromas += len(chroma_files)
        
        return {
            'total_skins': total_skins,
            'total_chromas': total_chromas,
            'total_ids': total_skins + total_chromas
        }
    

def download_skins_on_startup(
    target_dir: Path = None,
    force_update: bool = False,
    max_champions: Optional[int] = None,
    tray_manager=None,
    injection_manager=None,
    progress_callback: Optional[ProgressCallback] = None,
) -> bool:
    """Sync the skin library from LeagueSkins' manifest (only the files that differ are downloaded)"""
    try:
        # Note: Tray status is now managed by AppStatus class in main.py
        # This function just downloads and returns success/failure
        
        from utils.download.repo_downloader import download_skins_from_repo
        log.info("Syncing the skin library...")
        result = download_skins_from_repo(
            target_dir,
            force_update,
            tray_manager,
            progress_callback=progress_callback,
        )
        if injection_manager:
            injection_manager.initialize_when_ready()
        return result
        
    except Exception as e:
        log.error(f"Failed to download skins: {e}")
        if injection_manager:
            injection_manager.initialize_when_ready()
        return False

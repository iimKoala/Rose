"""The stats panel's window (main/stats_panel.py) can be drawn by Windows. No window is ever shown."""

import ctypes
import sys
import tkinter as tk
import unittest


@unittest.skipUnless(sys.platform == "win32", "the panel is a Windows window")
class StatsPanelWindowTest(unittest.TestCase):
    def test_windows_can_draw_the_panel_and_it_is_fully_solid(self):
        from main.stats_panel import StatsPanel

        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        panel = StatsPanel(root)
        user32 = ctypes.windll.user32
        window = user32.GetParent(panel.top.winfo_id())
        alpha = ctypes.c_ubyte(0)
        # This fails for a layered window that was never told how solid it is, and Windows draws nothing
        # of such a window: on Nov 14 the panel lost its "-alpha" and never appeared in two games
        self.assertTrue(user32.GetLayeredWindowAttributes(window, None, ctypes.byref(alpha), None))
        self.assertEqual(alpha.value, 255)


if __name__ == "__main__":
    unittest.main()

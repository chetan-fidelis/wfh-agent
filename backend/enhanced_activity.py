"""
Enhanced Activity Metrics Module
Tracks detailed user activity beyond basic key/mouse counts
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque


@dataclass
class EnhancedActivityStats:
    """Extended activity tracking with detailed metrics"""

    # Basic metrics (existing)
    key_presses: int = 0
    mouse_clicks: int = 0
    last_activity_ts: float = 0.0

    # Enhanced metrics
    scroll_events: int = 0
    window_switches: int = 0
    active_window_time: Dict[str, float] = field(default_factory=dict)
    typing_speed_wpm: float = 0.0
    mouse_distance_pixels: int = 0
    clipboard_operations: int = 0

    # Productivity indicators
    continuous_active_time: float = 0.0  # Seconds without idle break
    multitask_score: float = 0.0         # Window switch frequency
    focus_score: float = 0.0             # Time in single app ratio

    # Activity patterns
    hourly_activity: Dict[int, int] = field(default_factory=dict)  # hour -> activity_count
    peak_productivity_hours: List[int] = field(default_factory=list)

    # Internal tracking
    _last_mouse_pos: tuple = field(default_factory=lambda: (0, 0))
    _last_window: str = ""
    _last_typing_ts: float = 0.0
    _typing_buffer: deque = field(default_factory=lambda: deque(maxlen=100))


class ActivityTracker:
    """Enhanced activity tracking with detailed metrics"""

    def __init__(self, stats: EnhancedActivityStats):
        self.stats = stats
        self.lock = threading.Lock()

    def on_key_press(self):
        """Track keyboard activity with typing speed calculation"""
        with self.lock:
            now = time.time()
            self.stats.key_presses += 1
            self.stats.last_activity_ts = now

            # Calculate typing speed (WPM)
            self.stats._typing_buffer.append(now)
            if len(self.stats._typing_buffer) >= 5:
                time_span = self.stats._typing_buffer[-1] - self.stats._typing_buffer[0]
                if time_span > 0:
                    # Assume average 5 chars per word
                    words = len(self.stats._typing_buffer) / 5
                    self.stats.typing_speed_wpm = (words / time_span) * 60

            self.stats._last_typing_ts = now

    def on_mouse_click(self):
        """Track mouse clicks"""
        with self.lock:
            self.stats.mouse_clicks += 1
            self.stats.last_activity_ts = time.time()

    def on_mouse_scroll(self):
        """Track scroll events"""
        with self.lock:
            self.stats.scroll_events += 1
            self.stats.last_activity_ts = time.time()

    def on_mouse_move(self, x: int, y: int):
        """Track mouse movement distance"""
        with self.lock:
            if self.stats._last_mouse_pos != (0, 0):
                dx = x - self.stats._last_mouse_pos[0]
                dy = y - self.stats._last_mouse_pos[1]
                distance = int((dx**2 + dy**2)**0.5)
                self.stats.mouse_distance_pixels += distance

            self.stats._last_mouse_pos = (x, y)
            self.stats.last_activity_ts = time.time()

    def on_window_switch(self, window_title: str):
        """Track window switching and calculate focus metrics"""
        with self.lock:
            now = time.time()

            if self.stats._last_window and self.stats._last_window != window_title:
                self.stats.window_switches += 1

                # Calculate time in last window
                if self.stats.last_activity_ts > 0:
                    time_in_window = now - self.stats.last_activity_ts
                    app_name = self.stats._last_window.split('-')[-1].strip() if '-' in self.stats._last_window else self.stats._last_window
                    self.stats.active_window_time[app_name] = self.stats.active_window_time.get(app_name, 0) + time_in_window

            self.stats._last_window = window_title
            self.stats.last_activity_ts = now

            # Calculate multitask score (switches per hour)
            # Higher score = more multitasking
            self.stats.multitask_score = self.stats.window_switches / max(1, (now / 3600))

    def on_clipboard_operation(self):
        """Track clipboard copy/paste operations"""
        with self.lock:
            self.stats.clipboard_operations += 1
            self.stats.last_activity_ts = time.time()

    def calculate_focus_score(self) -> float:
        """Calculate focus score based on time distribution across apps"""
        with self.lock:
            if not self.stats.active_window_time:
                return 0.0

            total_time = sum(self.stats.active_window_time.values())
            if total_time == 0:
                return 0.0

            # Focus score = time in primary app / total time
            # Higher score = better focus
            max_time = max(self.stats.active_window_time.values())
            self.stats.focus_score = max_time / total_time
            return self.stats.focus_score

    def update_continuous_active_time(self, is_active: bool):
        """Track continuous activity without idle breaks"""
        with self.lock:
            now = time.time()

            if is_active and self.stats.last_activity_ts > 0:
                idle_time = now - self.stats.last_activity_ts
                if idle_time < 60:  # Less than 1 minute = continuous
                    self.stats.continuous_active_time += idle_time
                else:
                    self.stats.continuous_active_time = 0  # Reset on idle break
            else:
                self.stats.continuous_active_time = 0

    def update_hourly_activity(self):
        """Track activity distribution by hour"""
        with self.lock:
            from datetime import datetime
            current_hour = datetime.now().hour
            self.stats.hourly_activity[current_hour] = self.stats.hourly_activity.get(current_hour, 0) + 1

    def calculate_peak_hours(self) -> List[int]:
        """Identify peak productivity hours based on activity"""
        with self.lock:
            if not self.stats.hourly_activity:
                return []

            # Find top 3 hours with most activity
            sorted_hours = sorted(self.stats.hourly_activity.items(), key=lambda x: x[1], reverse=True)
            self.stats.peak_productivity_hours = [hour for hour, _ in sorted_hours[:3]]
            return self.stats.peak_productivity_hours

    def get_summary(self) -> dict:
        """Get comprehensive activity summary"""
        with self.lock:
            focus_score = self.calculate_focus_score()
            peak_hours = self.calculate_peak_hours()

            return {
                'basic': {
                    'key_presses': self.stats.key_presses,
                    'mouse_clicks': self.stats.mouse_clicks,
                    'scroll_events': self.stats.scroll_events,
                },
                'interaction': {
                    'window_switches': self.stats.window_switches,
                    'clipboard_operations': self.stats.clipboard_operations,
                    'mouse_distance_km': round(self.stats.mouse_distance_pixels / 1_000_000, 2),
                },
                'productivity': {
                    'typing_speed_wpm': round(self.stats.typing_speed_wpm, 1),
                    'continuous_active_minutes': round(self.stats.continuous_active_time / 60, 1),
                    'focus_score': round(focus_score * 100, 1),  # As percentage
                    'multitask_score': round(self.stats.multitask_score, 1),
                },
                'patterns': {
                    'peak_hours': peak_hours,
                    'top_apps': dict(sorted(
                        self.stats.active_window_time.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:5])
                }
            }

    def reset(self):
        """Reset all metrics"""
        with self.lock:
            self.stats = EnhancedActivityStats()

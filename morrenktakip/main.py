import cv2
import numpy as np
import pyautogui
import time
import tkinter as tk
from tkinter import ttk
import threading
import math
import sys
import os
import ctypes
from ctypes import wintypes, windll
import keyboard
import pygame
import gc

class RealTimeColorTracker:
    def __init__(self, gui):
        self.gui = gui
        
        # Purple color ranges - optimized for real-time detection
        self.purple_ranges = [
            ([180, 100, 200], [255, 180, 255]),  # Light purple
            ([150, 80, 180], [200, 150, 255]),   # Medium purple  
            ([120, 60, 160], [180, 120, 220]),   # Dark purple
            ([200, 150, 220], [255, 200, 255]),  # Pink-purple
            ([160, 120, 200], [220, 180, 255]),  # Lavender
            ([100, 40, 140], [160, 100, 200]),   # Deep purple
        ]
        
        self.tracking_distance = 30
        self.is_active = False
        self.running = True
        self.current_target = None
        
        # Performance optimization
        self.last_scan_time = 0
        self.scan_interval = 0.008  # 125 FPS max
        
        # Setup systems
        self.setup_pyautogui()
        self.setup_sound_system()
        self.setup_screen_api()
        self.setup_keyboard()
        self.start_tracking()
    
    def setup_pyautogui(self):
        """Configure PyAutoGUI for maximum speed"""
        pyautogui.FAILSAFE = False
        pyautogui.MINIMUM_DURATION = 0
        pyautogui.MINIMUM_SLEEP = 0
        pyautogui.PAUSE = 0
    
    def setup_sound_system(self):
        """Initialize sound system"""
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=256)
            self.load_sounds()
        except:
            self.open_sound = None
            self.close_sound = None
    
    def load_sounds(self):
        """Load sound files"""
        try:
            script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            sound_dir = os.path.join(script_dir, "sound")
            
            open_path = os.path.join(sound_dir, "open.mp3")
            close_path = os.path.join(sound_dir, "close.mp3")
            
            self.open_sound = pygame.mixer.Sound(open_path) if os.path.exists(open_path) else None
            self.close_sound = pygame.mixer.Sound(close_path) if os.path.exists(close_path) else None
        except:
            self.open_sound = None
            self.close_sound = None
    
    def play_sound(self, sound_type):
        """Play sound effect"""
        try:
            if sound_type == "open" and self.open_sound:
                self.open_sound.play()
            elif sound_type == "close" and self.close_sound:
                self.close_sound.play()
        except:
            pass
    
    def setup_screen_api(self):
        """Setup Windows API for direct screen access"""
        try:
            # High DPI awareness
            try:
                windll.shcore.SetProcessDpiAwareness(1)
            except:
                pass
            
            # Get screen dimensions
            self.screen_width = windll.user32.GetSystemMetrics(0)
            self.screen_height = windll.user32.GetSystemMetrics(1)
            
            # Setup device contexts for direct pixel access
            self.desktop_dc = windll.user32.GetDC(0)
            self.memory_dc = windll.gdi32.CreateCompatibleDC(self.desktop_dc)
            
            print(f"Screen API initialized: {self.screen_width}x{self.screen_height}")
        except Exception as e:
            print(f"Screen API setup failed: {e}")
            self.desktop_dc = None
            self.memory_dc = None
    
    def setup_keyboard(self):
        """Setup global keyboard listener"""
        try:
            keyboard.on_press_key('c', lambda e: self.toggle_tracking())
            print("Keyboard listener active - C key")
        except Exception as e:
            print(f"Keyboard setup failed: {e}")
    
    def capture_screen_realtime(self):
        """Real-time screen capture using Windows API"""
        try:
            # Method 1: Direct Windows API capture (fastest)
            if self.desktop_dc and self.memory_dc:
                try:
                    # Create bitmap
                    bitmap = windll.gdi32.CreateCompatibleBitmap(
                        self.desktop_dc, self.screen_width, self.screen_height)
                    old_bitmap = windll.gdi32.SelectObject(self.memory_dc, bitmap)
                    
                    # Copy screen to memory
                    windll.gdi32.BitBlt(
                        self.memory_dc, 0, 0, self.screen_width, self.screen_height,
                        self.desktop_dc, 0, 0, 0x00CC0020)
                    
                    # Get bitmap info
                    bmp_info = ctypes.create_string_buffer(40)
                    ctypes.memmove(bmp_info, ctypes.byref(ctypes.c_int(40)), 4)
                    ctypes.memmove(bmp_info[4:], ctypes.byref(ctypes.c_int(self.screen_width)), 4)
                    ctypes.memmove(bmp_info[8:], ctypes.byref(ctypes.c_int(-self.screen_height)), 4)
                    ctypes.memmove(bmp_info[12:], ctypes.byref(ctypes.c_short(1)), 2)
                    ctypes.memmove(bmp_info[14:], ctypes.byref(ctypes.c_short(32)), 2)
                    
                    # Get pixel data
                    data_size = self.screen_width * self.screen_height * 4
                    buffer = ctypes.create_string_buffer(data_size)
                    
                    result = windll.gdi32.GetDIBits(
                        self.desktop_dc, bitmap, 0, self.screen_height,
                        buffer, bmp_info, 0)
                    
                    # Cleanup
                    windll.gdi32.SelectObject(self.memory_dc, old_bitmap)
                    windll.gdi32.DeleteObject(bitmap)
                    
                    if result:
                        # Convert to numpy array
                        img_array = np.frombuffer(buffer, dtype=np.uint8)
                        img_array = img_array.reshape((self.screen_height, self.screen_width, 4))
                        # Convert BGRA to RGB
                        return img_array[:, :, [2, 1, 0]]
                        
                except Exception as e:
                    print(f"Windows API capture failed: {e}")
            
            # Method 2: PyAutoGUI fallback
            try:
                screenshot = pyautogui.screenshot()
                return np.array(screenshot)
            except Exception as e:
                print(f"PyAutoGUI capture failed: {e}")
                return None
                
        except Exception as e:
            print(f"Screen capture error: {e}")
            return None
    
    def find_purple_colors_realtime(self):
        """Real-time purple color detection"""
        try:
            # Throttle for performance
            current_time = time.time()
            if current_time - self.last_scan_time < self.scan_interval:
                return []
            self.last_scan_time = current_time
            
            # Capture screen
            img_array = self.capture_screen_realtime()
            if img_array is None or img_array.size == 0:
                return []
            
            # Create master mask for all purple ranges
            height, width = img_array.shape[:2]
            master_mask = np.zeros((height, width), dtype=np.uint8)
            
            # Check each purple range
            for lower, upper in self.purple_ranges:
                try:
                    lower_bound = np.array(lower, dtype=np.uint8)
                    upper_bound = np.array(upper, dtype=np.uint8)
                    range_mask = cv2.inRange(img_array, lower_bound, upper_bound)
                    master_mask = cv2.bitwise_or(master_mask, range_mask)
                except:
                    continue
            
            # Noise reduction
            try:
                kernel = np.ones((2,2), np.uint8)
                master_mask = cv2.morphologyEx(master_mask, cv2.MORPH_OPEN, kernel)
            except:
                pass
            
            # Find contours
            try:
                contours, _ = cv2.findContours(master_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            except:
                return []
            
            # Extract positions
            positions = []
            for contour in contours:
                try:
                    if cv2.contourArea(contour) >= 4:  # Minimum area
                        x, y, w, h = cv2.boundingRect(contour)
                        center_x = x + w // 2
                        center_y = y + h // 2
                        
                        if 0 <= center_x < width and 0 <= center_y < height:
                            positions.append((center_x, center_y))
                except:
                    continue
            
            # Cleanup
            del img_array, master_mask
            return positions
            
        except Exception as e:
            print(f"Color detection error: {e}")
            return []
    
    def find_closest_purple(self, purple_positions):
        """Find closest purple to current mouse position"""
        if not purple_positions:
            return None
        
        try:
            mouse_x, mouse_y = pyautogui.position()
            closest_pos = None
            min_distance = float('inf')
            
            for pos in purple_positions:
                distance = math.sqrt((mouse_x - pos[0])**2 + (mouse_y - pos[1])**2)
                if distance < min_distance:
                    min_distance = distance
                    closest_pos = pos
            
            return closest_pos, min_distance
        except:
            return None
    
    def move_mouse_instant(self, target_x, target_y):
        """Instant mouse movement (0ms)"""
        try:
            windll.user32.SetCursorPos(int(target_x), int(target_y))
        except:
            try:
                pyautogui.moveTo(target_x, target_y, duration=0)
            except:
                pass
    
    def tracking_loop(self):
        """Main real-time tracking loop"""
        print("Real-time tracking started - Live pixel detection active")
        print("Works with games, full-screen apps, and background applications!")
        
        gc_counter = 0
        
        while self.running:
            try:
                if self.is_active:
                    # Find all purple colors on screen (live detection)
                    purple_positions = self.find_purple_colors_realtime()
                    
                    if purple_positions:
                        # Find closest purple to mouse
                        result = self.find_closest_purple(purple_positions)
                        
                        if result:
                            closest_pos, distance = result
                            target_x, target_y = closest_pos
                            
                            # If within tracking distance, lock onto it
                            if distance <= self.tracking_distance:
                                self.move_mouse_instant(target_x, target_y)
                                status = f"TRACKING PURPLE ({target_x},{target_y})"
                            else:
                                status = f"PURPLE DETECTED ({int(distance)}px away)"
                                
                            try:
                                self.gui.update_status(status)
                            except:
                                pass
                        else:
                            try:
                                self.gui.update_status("ACTIVE - NO VALID TARGET")
                            except:
                                pass
                    else:
                        try:
                            self.gui.update_status("ACTIVE - NO PURPLE DETECTED")
                        except:
                            pass
                else:
                    try:
                        self.gui.update_status("INACTIVE")
                    except:
                        pass
                
                # Performance optimization
                if self.is_active:
                    time.sleep(0.003)  # 3ms - Very fast response
                else:
                    time.sleep(0.05)   # 50ms when inactive
                
                # Periodic cleanup
                gc_counter += 1
                if gc_counter % 2000 == 0:
                    gc.collect()
                    gc_counter = 0
                
            except Exception as e:
                print(f"Tracking error: {e}")
                time.sleep(0.01)
    
    def toggle_tracking(self):
        """Toggle tracking on/off"""
        try:
            self.is_active = not self.is_active
            status = "ACTIVE - Real-time Detection" if self.is_active else "INACTIVE"
            print(f"Tracking: {status}")
            
            # Play sound
            if self.is_active:
                self.play_sound("open")
            else:
                self.play_sound("close")
            
            # Update GUI
            try:
                self.gui.update_toggle_button()
            except:
                pass
                
        except Exception as e:
            print(f"Toggle error: {e}")
    
    def start_tracking(self):
        """Start tracking thread"""
        try:
            self.tracking_thread = threading.Thread(target=self.tracking_loop, daemon=True)
            self.tracking_thread.start()
            print("Real-time tracking thread started")
        except Exception as e:
            print(f"Thread start error: {e}")
    
    def stop_program(self):
        """Stop program"""
        print("Shutting down Real-time ColorBot...")
        self.running = False
        
        # Cleanup
        try:
            if hasattr(self, 'memory_dc') and self.memory_dc:
                windll.gdi32.DeleteDC(self.memory_dc)
            if hasattr(self, 'desktop_dc') and self.desktop_dc:
                windll.user32.ReleaseDC(0, self.desktop_dc)
        except:
            pass
        
        try:
            keyboard.unhook_all()
            pygame.mixer.quit()
        except:
            pass

class TrackerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🎯 ColorBot - Real-Time Purple Tracker")
        self.root.geometry("400x350")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        
        self.setup_ui()
        self.tracker = RealTimeColorTracker(self)
        
        print("=" * 60)
        print("🎯 REAL-TIME COLORBOT - LIVE PURPLE TRACKER")
        print("=" * 60)
        print("🟣 Target: ALL PURPLE TONES")
        print("🎮 WORKS WITH ALL GAMES & APPS!")
        print("⚡ INSTANT 0MS RESPONSE")
        print("👁️ LIVE PIXEL DETECTION")
        print("⌨️ C key: Toggle | ESC: Exit")
        print("=" * 60)
    
    def setup_ui(self):
        """Create simplified UI"""
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="🎯 REAL-TIME PURPLE TRACKER", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Features
        features_frame = ttk.LabelFrame(main_frame, text="🚀 FEATURES", padding="10")
        features_frame.pack(fill=tk.X, pady=(0, 15))
        
        features = [
            "⚡ Instant 0ms response time",
            "👁️ Live pixel detection",
            "🎮 Works with all games",
            "🖥️ Full-screen compatibility",
            "🎯 Real-time tracking"
        ]
        
        for feature in features:
            ttk.Label(features_frame, text=feature, font=("Arial", 9), 
                     foreground="green").pack(anchor=tk.W)
        
        # Target colors
        color_frame = ttk.LabelFrame(main_frame, text="TARGET COLORS", padding="10")
        color_frame.pack(fill=tk.X, pady=(0, 15))
        
        primary_frame = ttk.Frame(color_frame)
        primary_frame.pack()
        
        ttk.Label(primary_frame, text="Primary:").pack(side=tk.LEFT)
        primary_canvas = tk.Canvas(primary_frame, width=40, height=25, bg="#ee88fd")
        primary_canvas.pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(primary_frame, text="#ee88fd", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        
        ttk.Label(color_frame, text="🟣 All purple tones detected automatically", 
                 font=("Arial", 9), foreground="purple").pack(pady=(5, 0))
        
        # Status
        status_frame = ttk.LabelFrame(main_frame, text="STATUS", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.status_var = tk.StringVar(value="INACTIVE")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                     font=("Arial", 12, "bold"), foreground="red")
        self.status_label.pack()
        
        # Controls
        controls_frame = ttk.LabelFrame(main_frame, text="CONTROLS", padding="10")
        controls_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(controls_frame, text="C Key: Toggle Tracking", 
                 font=("Arial", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(controls_frame, text="ESC Key: Exit Program", 
                 font=("Arial", 10, "bold")).pack(anchor=tk.W)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(10, 0))
        
        self.toggle_button = ttk.Button(button_frame, text="🎯 START TRACKING", 
                                      command=self.toggle_tracking, width=18)
        self.toggle_button.pack(side=tk.LEFT, padx=5)
        
        exit_button = ttk.Button(button_frame, text="❌ EXIT", 
                               command=self.close_app, width=12)
        exit_button.pack(side=tk.LEFT, padx=5)
        
        # Bind ESC key
        self.root.bind('<Escape>', lambda e: self.close_app())
    
    def toggle_tracking(self):
        """Toggle tracking from GUI"""
        if hasattr(self, 'tracker'):
            self.tracker.toggle_tracking()
    
    def update_toggle_button(self):
        """Update toggle button text"""
        try:
            if hasattr(self, 'tracker') and self.tracker.is_active:
                self.toggle_button.config(text="⏸️ STOP TRACKING")
            else:
                self.toggle_button.config(text="🎯 START TRACKING")
        except:
            pass
    
    def update_status(self, status):
        """Update status display"""
        try:
            self.status_var.set(status)
            
            if "TRACKING" in status:
                self.status_label.config(foreground="green")
            elif "ACTIVE" in status:
                self.status_label.config(foreground="orange")
            else:
                self.status_label.config(foreground="red")
        except:
            pass
    
    def close_app(self):
        """Close application"""
        try:
            print("\n🔴 SHUTTING DOWN")
            if hasattr(self, 'tracker'):
                self.tracker.stop_program()
            self.root.quit()
            self.root.destroy()
        except:
            pass
        finally:
            try:
                sys.exit(0)
            except:
                os._exit(0)
    
    def run(self):
        """Run the GUI"""
        try:
            self.root.mainloop()
        except:
            self.close_app()

def main():
    """Main function"""
    try:
        print("🚀 Starting Real-Time ColorBot...")
        gui = TrackerGUI()
        gui.run()
    except KeyboardInterrupt:
        print("\n🔴 Program interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        print("🔴 ColorBot terminated")
        try:
            sys.exit(0)
        except:
            os._exit(0)

if __name__ == "__main__":
    main()
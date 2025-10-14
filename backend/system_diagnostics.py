"""
System Diagnostics Module for WFH Agent
Collects system information and installed applications for troubleshooting
"""

import os
import sys
import platform
import psutil
import json
import subprocess
from typing import Dict, List, Any
from datetime import datetime


class SystemDiagnostics:
    """Collects comprehensive system information for diagnostics"""

    def __init__(self):
        self.diagnostics = {}

    def collect_all(self) -> Dict[str, Any]:
        """Collect all diagnostic information"""
        self.diagnostics = {
            'timestamp': datetime.now().isoformat(),
            'system_info': self.get_system_info(),
            'cpu_info': self.get_cpu_info(),
            'memory_info': self.get_memory_info(),
            'disk_info': self.get_disk_info(),
            'network_info': self.get_network_info(),
            'processes': self.get_running_processes(),
            'installed_apps': self.get_installed_applications(),
            'startup_programs': self.get_startup_programs(),
            'agent_performance': self.get_agent_performance(),
            'user_activity_check': self.check_activity_detection()
        }
        return self.diagnostics

    def get_system_info(self) -> Dict[str, Any]:
        """Get basic system information"""
        try:
            return {
                'os': platform.system(),
                'os_version': platform.version(),
                'os_release': platform.release(),
                'platform': platform.platform(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'hostname': platform.node(),
                'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
                'uptime_hours': round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 2)
            }
        except Exception as e:
            return {'error': str(e)}

    def get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information and usage"""
        try:
            cpu_freq = psutil.cpu_freq()
            cpu_times = psutil.cpu_times_percent(interval=1)

            return {
                'physical_cores': psutil.cpu_count(logical=False),
                'logical_cores': psutil.cpu_count(logical=True),
                'max_frequency_mhz': round(cpu_freq.max, 2) if cpu_freq else 0,
                'current_frequency_mhz': round(cpu_freq.current, 2) if cpu_freq else 0,
                'cpu_usage_percent': psutil.cpu_percent(interval=1),
                'per_cpu_usage': psutil.cpu_percent(interval=1, percpu=True),
                'user_time_percent': round(cpu_times.user, 2),
                'system_time_percent': round(cpu_times.system, 2),
                'idle_percent': round(cpu_times.idle, 2)
            }
        except Exception as e:
            return {'error': str(e)}

    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory information"""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            return {
                'total_gb': round(mem.total / (1024**3), 2),
                'available_gb': round(mem.available / (1024**3), 2),
                'used_gb': round(mem.used / (1024**3), 2),
                'percent_used': mem.percent,
                'swap_total_gb': round(swap.total / (1024**3), 2),
                'swap_used_gb': round(swap.used / (1024**3), 2),
                'swap_percent': swap.percent
            }
        except Exception as e:
            return {'error': str(e)}

    def get_disk_info(self) -> Dict[str, Any]:
        """Get disk information"""
        try:
            partitions = []
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    partitions.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total_gb': round(usage.total / (1024**3), 2),
                        'used_gb': round(usage.used / (1024**3), 2),
                        'free_gb': round(usage.free / (1024**3), 2),
                        'percent_used': usage.percent
                    })
                except:
                    continue

            disk_io = psutil.disk_io_counters()
            return {
                'partitions': partitions,
                'io_read_mb': round(disk_io.read_bytes / (1024**2), 2) if disk_io else 0,
                'io_write_mb': round(disk_io.write_bytes / (1024**2), 2) if disk_io else 0
            }
        except Exception as e:
            return {'error': str(e)}

    def get_network_info(self) -> Dict[str, Any]:
        """Get network information"""
        try:
            net_io = psutil.net_io_counters()
            addrs = psutil.net_if_addrs()

            interfaces = []
            for iface, addresses in addrs.items():
                iface_info = {'name': iface, 'addresses': []}
                for addr in addresses:
                    iface_info['addresses'].append({
                        'family': str(addr.family),
                        'address': addr.address
                    })
                interfaces.append(iface_info)

            return {
                'bytes_sent_mb': round(net_io.bytes_sent / (1024**2), 2),
                'bytes_recv_mb': round(net_io.bytes_recv / (1024**2), 2),
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'interfaces': interfaces
            }
        except Exception as e:
            return {'error': str(e)}

    def get_running_processes(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """Get top N processes by CPU and memory usage"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    pinfo = proc.info
                    processes.append({
                        'pid': pinfo['pid'],
                        'name': pinfo['name'],
                        'cpu_percent': round(pinfo['cpu_percent'], 2),
                        'memory_percent': round(pinfo['memory_percent'], 2),
                        'status': pinfo['status']
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU usage
            processes_sorted = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)
            return processes_sorted[:top_n]
        except Exception as e:
            return [{'error': str(e)}]

    def get_installed_applications(self) -> List[Dict[str, str]]:
        """Get list of installed applications (Windows only)"""
        if platform.system() != 'Windows':
            return [{'error': 'Not Windows OS'}]

        try:
            apps = []

            # Method 1: Registry - Installed programs
            import winreg
            registry_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ]

            for reg_path in registry_paths:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                    for i in range(0, winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkey = winreg.OpenKey(key, subkey_name)

                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                publisher = ""
                                version = ""
                                install_date = ""

                                try:
                                    publisher = winreg.QueryValueEx(subkey, "Publisher")[0]
                                except:
                                    pass

                                try:
                                    version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                                except:
                                    pass

                                try:
                                    install_date = winreg.QueryValueEx(subkey, "InstallDate")[0]
                                except:
                                    pass

                                apps.append({
                                    'name': display_name,
                                    'publisher': publisher,
                                    'version': version,
                                    'install_date': install_date
                                })

                            except FileNotFoundError:
                                continue
                            finally:
                                winreg.CloseKey(subkey)

                        except Exception:
                            continue

                    winreg.CloseKey(key)

                except Exception:
                    continue

            # Remove duplicates and sort
            unique_apps = {app['name']: app for app in apps if app['name']}.values()
            return sorted(unique_apps, key=lambda x: x['name'])

        except Exception as e:
            return [{'error': str(e)}]

    def get_startup_programs(self) -> List[Dict[str, str]]:
        """Get list of startup programs"""
        if platform.system() != 'Windows':
            return [{'error': 'Not Windows OS'}]

        try:
            startup_apps = []
            import winreg

            # Check both user and machine startup locations
            registry_paths = [
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce")
            ]

            for hkey, reg_path in registry_paths:
                try:
                    key = winreg.OpenKey(hkey, reg_path)
                    for i in range(0, winreg.QueryInfoKey(key)[1]):
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            startup_apps.append({
                                'name': name,
                                'command': value,
                                'location': reg_path
                            })
                        except:
                            continue
                    winreg.CloseKey(key)
                except:
                    continue

            return startup_apps

        except Exception as e:
            return [{'error': str(e)}]

    def get_agent_performance(self) -> Dict[str, Any]:
        """Get WFH Agent's own performance metrics"""
        try:
            current_process = psutil.Process(os.getpid())

            return {
                'pid': current_process.pid,
                'name': current_process.name(),
                'cpu_percent': round(current_process.cpu_percent(interval=1), 2),
                'memory_mb': round(current_process.memory_info().rss / (1024**2), 2),
                'memory_percent': round(current_process.memory_percent(), 2),
                'threads': current_process.num_threads(),
                'open_files': len(current_process.open_files()),
                'connections': len(current_process.connections()),
                'create_time': datetime.fromtimestamp(current_process.create_time()).isoformat(),
                'status': current_process.status()
            }
        except Exception as e:
            return {'error': str(e)}

    def check_activity_detection(self) -> Dict[str, Any]:
        """Check if activity detection is working properly"""
        try:
            # Check if pynput is working
            from pynput import mouse, keyboard

            test_result = {
                'mouse_listener': 'Available',
                'keyboard_listener': 'Available',
                'activity_tracking': 'Operational'
            }

            # Check for common issues
            issues = []

            # Check if running as admin (can cause permission issues)
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if is_admin:
                issues.append("Running as Administrator - may cause activity detection issues")

            # Check CPU usage
            cpu_usage = psutil.cpu_percent(interval=1)
            if cpu_usage > 80:
                issues.append(f"High CPU usage ({cpu_usage}%) may affect activity detection")

            # Check memory pressure
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                issues.append(f"High memory usage ({mem.percent}%) may affect performance")

            test_result['issues'] = issues
            test_result['is_admin'] = is_admin

            return test_result

        except Exception as e:
            return {'error': str(e), 'activity_tracking': 'Failed'}

    def export_to_file(self, filepath: str = None):
        """Export diagnostics to JSON file"""
        if filepath is None:
            filepath = os.path.join(os.getcwd(), f'diagnostics_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.diagnostics, f, indent=2)

        return filepath

    def get_summary(self) -> str:
        """Get a human-readable summary of diagnostics"""
        if not self.diagnostics:
            self.collect_all()

        summary = []
        summary.append("=" * 60)
        summary.append("WFH AGENT SYSTEM DIAGNOSTICS REPORT")
        summary.append("=" * 60)

        # System Info
        sys_info = self.diagnostics.get('system_info', {})
        summary.append(f"\nSystem: {sys_info.get('platform', 'Unknown')}")
        summary.append(f"Hostname: {sys_info.get('hostname', 'Unknown')}")
        summary.append(f"Uptime: {sys_info.get('uptime_hours', 0)} hours")

        # CPU Info
        cpu_info = self.diagnostics.get('cpu_info', {})
        summary.append(f"\nCPU Cores: {cpu_info.get('logical_cores', 0)} ({cpu_info.get('physical_cores', 0)} physical)")
        summary.append(f"CPU Usage: {cpu_info.get('cpu_usage_percent', 0)}%")
        summary.append(f"CPU Frequency: {cpu_info.get('current_frequency_mhz', 0)} MHz")

        # Memory Info
        mem_info = self.diagnostics.get('memory_info', {})
        summary.append(f"\nMemory: {mem_info.get('used_gb', 0)}GB / {mem_info.get('total_gb', 0)}GB ({mem_info.get('percent_used', 0)}%)")

        # Agent Performance
        agent = self.diagnostics.get('agent_performance', {})
        summary.append(f"\nWFH Agent CPU: {agent.get('cpu_percent', 0)}%")
        summary.append(f"WFH Agent Memory: {agent.get('memory_mb', 0)}MB ({agent.get('memory_percent', 0)}%)")
        summary.append(f"Agent Threads: {agent.get('threads', 0)}")

        # Activity Detection
        activity = self.diagnostics.get('user_activity_check', {})
        summary.append(f"\nActivity Tracking: {activity.get('activity_tracking', 'Unknown')}")
        issues = activity.get('issues', [])
        if issues:
            summary.append("Issues Found:")
            for issue in issues:
                summary.append(f"  - {issue}")

        # Top Processes
        processes = self.diagnostics.get('processes', [])[:5]
        summary.append("\nTop 5 CPU Consuming Processes:")
        for proc in processes:
            summary.append(f"  - {proc.get('name', 'Unknown')}: CPU {proc.get('cpu_percent', 0)}%, Mem {proc.get('memory_percent', 0)}%")

        summary.append("\n" + "=" * 60)

        return "\n".join(summary)


if __name__ == '__main__':
    # Test the diagnostics module
    diag = SystemDiagnostics()
    diag.collect_all()

    # Print summary
    print(diag.get_summary())

    # Export to file
    filepath = diag.export_to_file()
    print(f"\nFull diagnostics exported to: {filepath}")

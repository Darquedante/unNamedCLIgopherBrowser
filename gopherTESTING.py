import json
import os
import socket
import logging
import time
import sys
from urllib.parse import urlparse

CONFIG_FILE = 'config.json'
BOOKMARKS_FILE = 'bookmarks.json'
SEARCH_ENGINES_FILE = 'search_engines.json'
HISTORY_FILE='navigation_history.json'

class ImprovedHistoryManager:
    def __init__(self, max_history=5, history_file=None):
        self.backward_history = []
        self.forward_history = []
        self.max_history = max_history
        self.history_file = history_file

    def record(self, address):
        """Record an address in the history."""
        self.backward_history.append(address)
        self.forward_history = []

    def add_page(self, page):
        """Add a page to the history."""
        print(f"Attempting to add: {page}")
        if not self.backward_history or self.backward_history[-1] != page:
            if len(self.backward_history) == self.max_history:
                self.backward_history.pop(0)
            self.backward_history.append(page)
            self.forward_history.clear()
        else:
            print("Page already exists in history. Not adding.")
        self._debug_history()

    def go_back(self):
        """Go back in history and return the previous address."""
        if not self.backward_history:
            return None

        last_address = self.backward_history.pop()
        self.forward_history.append(last_address)

        # Add a debug log here to check the state of backward_history
        self.logging.debug(f"History after going back: {self.backward_history}")

        if self.backward_history:
            return self.backward_history[-1]
        return None

    def go_forward(self):
        """Pop and return the last page from forward history and push it to backward history."""
        if not self.forward_history:
            return None
        next_page = self.forward_history.pop()
        self.backward_history.append(next_page)
        self._save_history()
        self._debug_history()
        return next_page

    def _debug_history(self):
        print("------ History Debug Info ------")
        print(f"Backward History: {self.backward_history}")
        print(f"Forward History: {self.forward_history}")
        print("--------------------------------")

    def _save_history(self):
        """Save current history state to the history file."""
        if self.history_file:
            with open(self.history_file, 'w') as f:
                json.dump({
                    'backward': self.backward_history,
                    'forward': self.forward_history
                }, f)
                print("History saved.")

class GopherClient:
    def __init__(self, host='1436.ninja', port=70, timeout=10, debug=False):
        logging.basicConfig(level=logging.DEBUG if debug else logging.WARNING)
        self.logging = logging.getLogger('GopherClient')
        self.host = host
        self.port = port
        self.timeout = timeout
        self.debug = debug
        self.socket = None
        self.bookmarks = self.load_bookmarks()
        self.search_engines = self.load_search_engines()
        self.history_manager = ImprovedHistoryManager(history_file=HISTORY_FILE)
        self.is_navigating_back = False

    def _debug_print(self, message):
        if self.debug:  # Check if debug mode is on
            self.logging.debug(message)

    @staticmethod
    def valid_hostname(hostname):
        if not 1 < len(hostname) < 253:
            return False
        for label in hostname.split("."):
            if not (1 <= len(label) <= 63) or not label[-1].isalnum() or not label[0].isalnum() or label.startswith(
                    '-') or label.endswith('-'):
                return False

        return True

    def connect_to_server(self):
        host = input("Enter Gopher server hostname: ").strip()
        if not host:
            return
        self.host = host
        self.port = 70  # default Gopher port
        self._establish_connection()
        # Provide an empty string as the selector to fetch the root directory/main menu
        self.navigate(selector="", server=self.host, port=self.port)

    def list_search_engines(self):
        for engine in self.search_engines:
            print(engine['name'])

    def search_gopherspace(self):
        engine = input("Choose a search engine (e.g., 'Veronica-2', 'Contrition - All Types'): ").strip()
        if engine in [e['name'] for e in self.search_engines]:
            query = input("Enter search query: ").strip()
            self.search(query, engine)
        else:
            print(f"Search engine {engine} not found.")

    def quit_client(self):
        if self.socket:
            self.socket.close()
        exit(0)

    def toggle_debug_mode(self):
        self.debug = not self.debug
        if self.debug:
            self.logging.setLevel(logging.DEBUG)  # Set logger level to DEBUG
        else:
            self.logging.setLevel(logging.WARNING)  # Set logger level to WARNING or any other level you prefer
        print(f"Debug mode {'ON' if self.debug else 'OFF'}")

    def run(self):
        """Main loop to interact with the user."""
        options = {
            "1": ("Connect to a Gopher server", self.connect_to_server),
            "2": ("Search Gopherspace", self.search_gopherspace),
            "3": ("List bookmarks", self.list_bookmarks),
            "4": ("Navigate to a bookmarked server", self.navigate_to_bookmark),  # Added this line
            "5": ("Save configuration", self.save_config),
            "6": ("Load configuration", self.load_config),
            "7": ("Quit", self.quit_client),
            "8": ("Help", self.display_help),
            "9": ("Toggle Debug Mode", self.toggle_debug_mode)
        }

        while True:
            print("\nOptions:")
            for key, (description, _) in options.items():
                print(f"{key}. {description}")
            choice = input("> ").strip()

            action = options.get(choice, (None, None))[1]
            if action:
                action()
            else:
                print("Invalid choice. Please try again.")

    def connect(self, host=None, port=None):
        if host:
            self.host = host
        if port:
            self.port = port
        self._establish_connection()

    def navigate(self, selector, record_history=True, server=None, port=70):
        self._ensure_connection()
        self.logging.debug(f"Navigating with selector: {selector}")

        # Debug statement to monitor the history state during navigation
        self.logging.debug(f"Current history state: {self.history_manager.backward_history}")

        try:
            data = self._send_request(selector, server, port)
            if not data:
                return

            if '\t' in data:
                selected_selector, new_server, new_port = self._display_gopher_menu(data)
                if selected_selector is not None:
                    navigate_server = new_server if new_server else self.host
                    navigate_port = int(new_port) if new_port else self.port
                    return self.navigate(selected_selector, record_history=False, server=navigate_server, port=navigate_port)
                else:
                    action = self._handle_user_choice(data)
                    if action == "BACK":
                        # Debug statement to monitor the history state before going back
                        self.logging.debug(
                            f"Current history state before going back: {self.history_manager.backward_history}")
                        return
            else:
                action = self._handle_user_choice(data)
                if action == "BACK":
                    # Debug statement to monitor the history state before going back
                    self.logging.debug(
                        f"Current history state before going back: {self.history_manager.backward_history}")
                    return

            # Record the navigation history if the flag is set
            if record_history:
                current_address = (server, port)
                self.history_manager.record(current_address)
                # Add a debug log here to check the state of backward_history after each navigation
                self.logging.debug(f"History after navigation: {self.history_manager.backward_history}")

        except Exception as e:
            self._error_handler(f"Error while navigating: {e}", debug_info=e)

    def _handle_user_choice(self, data):
        """
        Handle the choice when a user encounters a non-menu item.
        """
        self.logging.debug("Handling user choice for non-menu data.")
        print(data)

        while True:
            choice = input("\nPress 'b' to go back or 'q' to quit:\n> ").strip().lower()

            if choice == 'b':
                previous_page = self.history_manager.go_back()
                if previous_page:
                    parsed_url = urlparse(previous_page)
                    self.navigate(parsed_url.path, record_history=False, server=parsed_url.hostname,
                                  port=parsed_url.port)
                    return "BACK"  # Indicate that we're going back
                else:
                    print("You're at the beginning of your navigation history.")
            elif choice == 'q':
                sys.exit(0)
            else:
                print("Invalid choice. Please try again.")

    def go_forward(self):
        """Navigate forward (after going back)."""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            selector = self.history[self.history_index]
            self.navigate(selector)
        else:
            print("You're at the end of your navigation history.")

    def load_search_engines(self):
        """Load available search engines from a configuration file."""
        return self._load_from_file(SEARCH_ENGINES_FILE)

    def search(self, query, engine):
        """Search the Gopher server."""
        search_engine = next((e for e in self.search_engines if e['name'] == engine), None)
        if not search_engine:
            print(f"Search engine {engine} not found.")
            return

        hostname = search_engine['hostname']
        port = search_engine.get('port', 70)  # Use port 70 as default if not specified
        selector = search_engine['selector'] + query

        # Connect to the search engine's server and send the search query
        self.host = hostname
        self.port = port
        self.connect()
        data = self._send_request(selector)

        if data:
            # Navigate to the search results without recording history
            self.navigate(selector, record_history=False)

    def save_bookmark(self, title, selector):
        existing = [bookmark for bookmark in self.bookmarks if bookmark['selector'] == selector]
        if existing:
            print(f"'{title}' is already bookmarked.")
            return
        self.bookmarks.append({'title': title, 'selector': selector})
        self._save_to_file(BOOKMARKS_FILE, self.bookmarks)
        print(f"Saved '{title}' as a bookmark.")

    def delete_bookmark(self, index):
        """Delete a bookmark by its index."""
        try:
            deleted_bookmark = self.bookmarks.pop(index)
            self._save_to_file(BOOKMARKS_FILE, self.bookmarks)
            print(f"Deleted bookmark '{deleted_bookmark['title']}'.")
        except IndexError:
            print("Invalid bookmark index.")

    def modify_bookmark(self, index, new_title=None, new_selector=None):
        """Modify a bookmark by its index."""
        try:
            bookmark = self.bookmarks[index]
            if new_title:
                bookmark['title'] = new_title
            if new_selector:
                bookmark['selector'] = new_selector
            self._save_to_file(BOOKMARKS_FILE, self.bookmarks)
            print(f"Modified bookmark to '{bookmark['title']}' - '{bookmark['selector']}'.")
        except IndexError:
            print("Invalid bookmark index.")

    def list_bookmarks(self):
        """Display all saved bookmarks."""
        if not self.bookmarks:
            print("No bookmarks saved.")
            return
        for index, bookmark in enumerate(self.bookmarks):
            print(f"{index}. {bookmark['title']} ({bookmark['selector']})")

    def visit_bookmark(self, index):
        """Navigate to a bookmark by its index."""
        try:
            bookmark = self.bookmarks[index]
            self.navigate(bookmark['selector'])
        except IndexError:
            print("Invalid bookmark index.")

    def load_bookmarks(self):
        """Load bookmarks from a local file."""
        return self._load_from_file(BOOKMARKS_FILE)

    def save_config(self):
        """Save configuration to a local file."""
        config = {
            'hostname': self.host,
            'port': self.port,
            'backward_history': self.history_manager.backward_history,
            'forward_history': self.history_manager.forward_history
        }
        self._save_to_file(CONFIG_FILE, config)
        print(f"Configuration saved to {CONFIG_FILE}.")

    def load_config(self):
        """Load configuration from a local file."""
        config = self._load_from_file(CONFIG_FILE)
        self.host = config.get('hostname', self.host)
        self.port = config.get('port', self.port)
        self.history_manager.backward_history = config.get('backward', self.history_manager.backward_history)
        self.history_manager.forward_history = config.get('forward', self.history_manager.forward_history)

    def display_help(self):
        """Display usage instructions."""
        print("\nGopher Client Help:")
        print("---------------------")
        print("1. Connect to a Gopher server: Connect to a specified Gopher server using the provided hostname.")
        print("2. Search Gopherspace: Search the Gopherspace using a chosen search engine and query.")
        print("3. List bookmarks: Display all saved bookmarks with their titles and selectors.")
        print("4. Navigate to a bookmarked server: Navigate to a bookmarked Gopher server using its selector.")
        print(
            "5. Save configuration: Save the current configuration (connected server, port, backward and forward history) to a file.")
        print("6. Load configuration: Load the saved configuration from a file.")
        print("7. Quit: Exit the Gopher client application.")
        print("\nNavigation Help:")
        print("---------------------")
        print("While viewing a Gopher menu:")
        print("- Enter the number corresponding to a menu item to select it.")
        print("- Enter 'b' to go back to the previous menu or content.")
        print("- Enter 'q' to quit the application.")
        print("\nNote: Always ensure you're connected to a server before attempting to navigate or search.")

    def navigate_to_bookmark(self):
        """Navigate to a bookmark by its index."""
        self.list_bookmarks()
        try:
            choice = int(input("Enter the number of the bookmark you want to navigate to: "))
            bookmark = self.bookmarks[choice]
            self.navigate(bookmark['selector'])
        except (ValueError, IndexError):
            print("Invalid choice. Please select a valid bookmark number.")

    def _split_address(self, address):
        # Remove the 'gopher://' prefix if it exists
        if address.startswith("gopher://"):
            address = address[len("gopher://"):]

        # Split based on the first '/'
        parts = address.split('/', 1)
        server_port = parts[0]
        selector = parts[1] if len(parts) > 1 else ""

        # If ':' is present, then we have a port number
        if ':' in server_port:
            server, port = server_port.split(':', 1)
        else:
            server = server_port
            port = "70"  # Default Gopher port as string

        return server, port, selector

    def _go_back(self):
        """Navigate back to the previous page."""
        print("Attempting to go back...")

        # Validating history data: Ensure backward_history contains valid URLs
        if not self.history_manager.backward_history:
            print("You're at the beginning of your navigation history.")
            return

        prev_page = self.history_manager.go_back()

        # Validating history data: Ensure history_manager.go_back() returns valid URLs
        if not prev_page:
            print("You're at the beginning of your navigation history.")
            return

        server, port, selector = self._split_address(prev_page)
        self.logging.debug(f"Going back to: {server}:{port}/{selector}")
        self.navigate(selector, record_history=False, server=server, port=port)

    def _error_handler(self, error_message, error_type="General", debug_info=None):
        self.logging.error(f"{error_type} Error: {error_message}", exc_info=True)

    def _is_connected(self):
        """Check if the connection is alive."""
        try:
            # Check if socket is still connected
            return self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0
        except (socket.error, AttributeError):
            return False

    def _establish_connection(self, server=None, port=None):
        try:
            start_time = time.time()
            if self.socket:
                self.socket.close()
            self.logging.debug(
                f"[{self._establish_connection.__name__}:{self._establish_connection.__code__.co_firstlineno}] Attempting to establish connection to {server or self.host}:{port or self.port}")
            self.socket = socket.create_connection((server or self.host, port or self.port), self.timeout)
            self.logging.debug(
                f"[{self._establish_connection.__name__}:{self._establish_connection.__code__.co_firstlineno}] Connection established to {server or self.host}:{port or self.port} in {time.time() - start_time:.2f} seconds")
        except socket.error as e:
            self._error_handler(f"Error establishing connection: {e}", debug_info=e)

    def _ensure_connection(self):
        if not self._is_connected():
            self.logging.debug(
                f"[{self._ensure_connection.__name__}:{self._ensure_connection.__code__.co_firstlineno}] Connection lost. Reconnecting...")
            self.connect(self.host, self.port)

    def _send_request(self, selector, server=None, port=None):
        start_time = time.time()
        response = b""
        self._debug_print(
            f"[{self._send_request.__name__}:{self._send_request.__code__.co_firstlineno}] Sending request with selector: {selector}")

        try:
            if not server:
                server = self.host
            if not port:
                port = self.port

            self._establish_connection(server, port)  # Pass the server and port to the connection method
            self.socket.sendall((selector + "\r\n").encode())

            while True:
                chunk = self.socket.recv(4096)
                if not chunk:
                    break
                response += chunk

            self.socket.close()

            decoded_response = response.decode('utf-8', errors='replace')
            self.logging.debug(
                f"[{self._send_request.__name__}:{self._send_request.__code__.co_firstlineno}] Received response: {decoded_response[:100]}...")
            self.logging.debug(
                f"[{self._send_request.__name__}:{self._send_request.__code__.co_firstlineno}] _send_request took {time.time() - start_time:.2f} seconds to execute")
            return decoded_response
        except (socket.error, Exception) as e:
            self._error_handler(f"Error: {e}")
            return None

    def _parse_gopher_menu(self, menu_data):
        self.logging.debug(
            f"[{self._parse_gopher_menu.__name__}:{self._parse_gopher_menu.__code__.co_firstlineno}] Parsing gopher menu: {menu_data[:100]}...")
        entries = []
        lines = menu_data.split("\n")
        for line in lines:
            parts = line.split("\t")
            if len(parts) >= 4:
                entry_type = parts[0][0]
                display_string = parts[0][1:]
                selector = parts[1]
                server = parts[2]
                port = parts[3]
                entries.append((entry_type, display_string, selector, server, port))
        return entries

    def _get_user_choice(self, entries):
        while True:
            choice = input("Select an option: ")
            self.logging.debug(f"User selected choice: {choice}")

            if choice.isdigit() and 0 <= int(choice) < len(entries):
                return entries[int(choice)]
            elif choice == 'b':
                # Ensuring _go_back is being called
                self._go_back()
                # Since we're going back, we should not process further in the current navigation flow.
                return None, None, None
            elif choice == 'q':
                self.quit_client()
            print("Invalid choice. Please try again.")

    def _display_gopher_menu(self, data):
        lines = data.split("\n")
        menu_line_count = sum(
            1 for line in lines if line.count('\t') >= 3)  # A valid gopher menu line has at least 3 tabs

        # Check if at least 20% of the lines seem to represent a menu
        if menu_line_count > len(lines) * 0.20:
            entries = self._parse_gopher_menu(data)
            self._print_gopher_menu(entries)
            selected_item = self._get_user_choice(entries)
            if selected_item:
                _, _, selector, server, port = selected_item if len(selected_item) == 5 else (
                None, None, None, None, None)
                if port:
                    port = int(port.strip())  # Strip any whitespace or carriage return and convert to integer
                return selector, server, port
            return None, None, None
        else:
            # Handle cases where data doesn't seem to be a Gopher menu
            print(data)
            print("\nPress 'b' to go back or 'q' to quit:")
            return None, None, None

    def _print_gopher_menu(self, entries):
        for index, (entry_type, display_string, _, _, _) in enumerate(entries):
            prefix = "[LINK]" if entry_type == "1" else "[TEXT]" if entry_type == "0" else ""
            print(f"{index}. {prefix} {display_string}")
        print("q. Quit")
        print("b. Go back")

    def _load_from_file(self, filename, default_value=[]):
        if not os.path.exists(filename):
            return default_value
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except IOError as e:
            self.logging.error(f"Error opening or reading from {filename}: {e}")
        except json.JSONDecodeError as e:
            self.logging.error(f"Error decoding JSON from {filename}: {e}")
        except Exception as e:
            self.logging.error(f"Unexpected error reading from {filename}: {e}")
        return default_value

    def _save_to_file(self, filename, data):
        self.logging.debug(
            f"[{self._save_to_file.__name__}:{self._save_to_file.__code__.co_firstlineno}] Saving data to {filename}")

        # Backup original file
        backup_filename = filename + ".bak"
        if os.path.exists(filename):
            try:
                import shutil
                shutil.copy2(filename, backup_filename)
            except Exception as e:
                self.logging.error(f"Error while creating a backup: {e}")
                return

        # Try to save the new data
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
        except (IOError, json.JSONDecodeError) as e:
            self.logging.error(f"Error while saving data to {filename}: {e}")

            # Restore from backup in case of any error
            if os.path.exists(backup_filename):
                try:
                    shutil.copy2(backup_filename, filename)
                except Exception as restore_error:
                    self.logging.error(f"Error while restoring from backup: {restore_error}")
                    return
            return

        # If everything went fine, remove the backup
        if os.path.exists(backup_filename):
            try:
                os.remove(backup_filename)
            except Exception as remove_error:
                self.logging.error(f"Error while removing backup: {remove_error}")


def main():
    # Print the current working directory
    print(f"Current working directory: {os.getcwd()}")

    client = GopherClient()

    # Forcefully generate a log entry
    client.logging.debug("This is a debug log entry.")

    client.run()


if __name__ == '__main__':
    main()
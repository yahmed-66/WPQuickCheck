# Default libraries
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin
# From requirements.txt
from colorama import Back, Fore, Style, init
from curl_cffi import requests

init(autoreset=True) # colorama funkiness

REDIRECT_STATUSES = {301, 302, 303, 307, 308}

WP_CRITICAL_FILES = [
    "wp-includes/version.php",
    "wp-includes/class-wp.php",
    "wp-includes/functions.php",
    "wp-includes/plugin.php",
    "wp-includes/load.php",
    "wp-includes/default-constants.php",
    "wp-includes/cron.php",
    "wp-includes/class-wp-user.php",
    "wp-includes/class-wp-roles.php",
    "wp-includes/class-wp-session-tokens.php",
    "wp-includes/rest-api.php",
    "wp-includes/vars.php",
    "wp-includes/kses.php",
    "wp-includes/capabilities.php",
    "wp-includes/option.php",
]

# Abstracts the GET request process
def make_request(url, allow_redirects=True):
    try:
        response = requests.get(
            url,
            allow_redirects=allow_redirects,
            impersonate="chrome",
        )
        return response
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}An error occurred while making the request:{Style.RESET_ALL}")
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)

# Abstracts the POST request process
def make_post_request(url, data, headers=None, allow_redirects=True):
    try:
        return requests.post(
            url,
            data=data,
            headers=headers or {},
            allow_redirects=allow_redirects,
            impersonate="chrome",
        )
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}An error occurred while making the request:{Style.RESET_ALL}")
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)

# Find a usable Chromium-compatible browser binary
def find_chrome():
    candidates = [
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    for binary in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        shim = shutil.which(binary)
        if shim:
            real = Path(shim).resolve()
            if real.exists():
                candidates.insert(0, str(real))
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None

# Run gowitness scan file (screenshots only). Requires gowitness on PATH.
def run_gowitness_file_scan(urls, gowitness_bin, screenshot_dir):
    screenshot_dir = Path(screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    unique = list(dict.fromkeys(u.strip() for u in urls if u.strip()))
    if not unique:
        return
    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="wpquickcheck_urls_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(unique) + "\n")
        cmd = [
            gowitness_bin,
            "scan",
            "file",
            "-f", tmp_path,
            "-s", str(screenshot_dir),
            "--write-none",
            "-q",
        ]
        chrome = find_chrome()
        if chrome:
            cmd += ["--chrome-path", chrome]
        else:
            print(f"{Fore.YELLOW}No Chrome/Chromium binary found; gowitness may fail.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Install Chromium: brew install --cask chromium{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{Style.BRIGHT}Running gowitness on {len(unique)} URL(s)...{Style.RESET_ALL}")
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            print(f"{Fore.RED}gowitness exited with code {completed.returncode}{Style.RESET_ALL}")
            if completed.stdout:
                print(completed.stdout)
            if completed.stderr:
                print(completed.stderr)
        else:
            print(f"{Fore.GREEN}Screenshots saved to:{Style.RESET_ALL} {screenshot_dir}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

# Scan critical wp-includes files, print findings, and save exposed files to disk.
def scan_wp_includes(base_url, output_location, found_misconfigs):
    save_dir = Path(output_location) / "wp-includes-loot"
    save_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{Fore.CYAN}{Style.BRIGHT}Scanning critical wp-includes files...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{Style.BRIGHT}Saving exposed files to: {save_dir}{Style.RESET_ALL}\n")

    for wp_file in WP_CRITICAL_FILES:
        file_url = f"{base_url}{wp_file}"
        try:
            response = make_request(file_url)

            if response.status_code == 200:
                content = response.text.strip()
                print(f"{Fore.GREEN}Found {file_url}{Style.RESET_ALL} ")
                # Save to disk
                filename = os.path.basename(wp_file)
                save_path = save_dir / filename
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
                print(f"{Fore.GREEN}Saved: {save_path}{Style.RESET_ALL}")

                found_misconfigs.append(file_url)

            elif response.status_code == 403:
                print(f"{Fore.YELLOW}[FORBIDDEN]{Style.RESET_ALL} {file_url} (exists but access denied)")

            else:
                print(f"{Fore.WHITE}[{response.status_code}]{Style.RESET_ALL} {file_url}")

        except Exception as e:
            print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} Failed to fetch {file_url}: {e}")

    # Dedicated wp-cron warning
    cron_url = f"{base_url}wp-includes/cron.php"
    response = make_request(cron_url)
    if response.status_code == 200:
        print(f"\n{Fore.RED}[!] wp-cron.php is publicly accessible — potential DoS vector!{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}Done. Files saved to: {save_dir}{Style.RESET_ALL}\n")


if "__main__" == __name__:
    if len(sys.argv) < 3:
        print(f"{Fore.CYAN}Usage: python3 {Path(sys.argv[0]).name} <url> <output-location>{Style.RESET_ALL}")
        sys.exit(1)

    url = sys.argv[1]
    output_location = sys.argv[2]

    gowitness_bin = shutil.which("gowitness")
    if gowitness_bin:
        print(f"{Fore.GREEN}gowitness found:{Style.RESET_ALL} {gowitness_bin}")
    else:
        print(f"{Fore.YELLOW}gowitness not found in PATH; screenshots will be skipped at the end.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Install: https://github.com/sensepost/gowitness{Style.RESET_ALL}")

    try:
        response = make_request(url)
        if "wordpress" not in response.text.lower():
            if "wp" not in response.text.lower():
                print(f"{Fore.YELLOW}{Style.BRIGHT}WordPress may not be installed, would you like to continue anyways?{Style.RESET_ALL}")
            else:
                print(f"{Fore.CYAN}{Style.BRIGHT}WordPress not detected, would you like to continue anyways?{Style.RESET_ALL}")
            answer = input(f"{Fore.CYAN}{Style.BRIGHT}y/n: {Style.RESET_ALL}").lower().strip()
            if answer != "y":
                print(f"{Fore.GREEN}{Style.BRIGHT}Exiting...{Style.RESET_ALL}")
                sys.exit(1)

        print(f"{Fore.CYAN}{Style.BRIGHT}Where is WordPress installed? (Default will search for / and /wp/){Style.RESET_ALL}")
        wp_install_path = input(f"{Fore.CYAN}Enter the path: ").lower().strip()
        search_paths = [wp_install_path] if wp_install_path else ['/', '/wp/']

        found_misconfigs = []
        wp_includes_loot = []
        for search_path in search_paths:
            print(f"{Fore.CYAN}{Style.BRIGHT}Searching for WordPress in {search_path}{Style.RESET_ALL}")
            base_url = url + search_path

            print(f"{Fore.CYAN}{Style.BRIGHT}Checking common WordPress files:{Style.RESET_ALL}")

            # Check wp-admin
            response = make_request(f"{base_url}wp-admin", allow_redirects=False)
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress admin page found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-admin")
            elif response.status_code in REDIRECT_STATUSES:
                loc = (response.headers.get("Location") or "").strip()
                target = urljoin(response.url, loc)
                if "wp-login.php" in target.lower():
                    print(f"{Fore.GREEN}WordPress admin redirects to login (wp-login.php):{Style.RESET_ALL}", target)
                    found_misconfigs.append(f"{base_url}wp-admin")
                else:
                    print(f"{Fore.GREEN}Redirect from wp-admin, but not to wp-login.php:", target)

            # Check wp-includes.php and wp-includes directory — scan critical files if either is exposed
            wp_includes_exposed = False
            response = make_request(f"{base_url}wp-includes.php")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress includes page found (wp-includes.php){Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-includes.php")
                wp_includes_exposed = True

            response = make_request(f"{base_url}wp-includes")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress includes directory found (wp-includes){Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-includes")
                wp_includes_exposed = True

            if wp_includes_exposed:
                scan_wp_includes(base_url, output_location, wp_includes_loot)

            # Check wp-json
            response = make_request(f"{base_url}wp-json")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress JSON data found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-json")
                response = make_request(f"{base_url}wp-json/wp/v2/users")
                if response.status_code == 200:
                    print(f"{Fore.GREEN}WordPress users found{Style.RESET_ALL}")
                    found_misconfigs.append(f"{base_url}wp-json/wp/v2/users")

            # Check wp-config.php
            response = make_request(f"{base_url}wp-config.php")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress config file found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-config.php")

            # Check wp-content
            response = make_request(f"{base_url}wp-content")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress content found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-content")

            # Check wp-content/plugins
            response = make_request(f"{base_url}wp-content/plugins")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress plugins found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-content/plugins")

            # Check wp-content/themes
            response = make_request(f"{base_url}wp-content/themes")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress themes found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-content/themes")

            # Check wp-content/uploads
            response = make_request(f"{base_url}wp-content/uploads")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress uploads found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}wp-content/uploads")

            # Check license.txt
            response = make_request(f"{base_url}license.txt")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress license file found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}license.txt")

            # Check readme.html
            response = make_request(f"{base_url}readme.html")
            if response.status_code == 200:
                print(f"{Fore.GREEN}WordPress readme file found{Style.RESET_ALL}")
                found_misconfigs.append(f"{base_url}readme.html")

            # User ID enumeration
            print(f"{Fore.CYAN}{Style.BRIGHT}Checking for user ID enumeration (this might take some time...){Style.RESET_ALL}")
            for user_id in range(1, 100):
                response = make_request(f"{base_url}?author={user_id}")
                if response.status_code == 200:
                    print(f"{Fore.GREEN}User ID enumeration found:{Style.RESET_ALL} {base_url}?author={user_id}")
                    found_misconfigs.append(f"{base_url}?author={user_id}")
                    break
            if found_misconfigs:
                if "author" not in found_misconfigs[-1]:
                    print(f"{Fore.RED}User ID enumeration not found{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}User ID enumeration not found{Style.RESET_ALL}")


            # Check xmlrpc.php
            print(f"{Fore.CYAN}{Style.BRIGHT}Checking xmlrpc.php...{Style.RESET_ALL}")
            xmlrpc_url = f"{base_url}xmlrpc.php"
            xmlrpc_body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<methodCall>"
                "<methodName>system.listMethods</methodName>"
                "<params></params>"
                "</methodCall>"
            )
            response = make_post_request(
                xmlrpc_url,
                data=xmlrpc_body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            if response.status_code == 200:
                text = response.text
                if "XML-RPC services are disabled" in text:
                    print(f"{Fore.RED}XML-RPC appears disabled on this site{Style.RESET_ALL}")
                elif "<methodResponse>" in text:
                    print(f"{Fore.GREEN}XML-RPC is responding (xmlrpc.php accepts POST){Style.RESET_ALL}")
                    found_misconfigs.append(f"{base_url}xmlrpc.php")
                    if "<string>pingback.ping</string>" in text or ">pingback.ping<" in text:
                        print(
                            f"{Fore.GREEN}{Style.BRIGHT}pingback.ping is exposed via XML-RPC: "
                            f"the site may fetch attacker-chosen URLs (potential SSRF attack vector)."
                            f"{Style.RESET_ALL}"
                        )
                else:
                    print(f"{Fore.RED}{Style.BRIGHT}Unexpected response from xmlrpc.php (not standard XML-RPC XML){Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}xmlrpc.php returned HTTP {response.status_code}{Style.RESET_ALL}")

        if found_misconfigs:
            print(f"{Fore.CYAN}{Style.BRIGHT}Findings ({len(found_misconfigs) + len(wp_includes_loot)}):{Style.RESET_ALL}")
            for item in found_misconfigs:
                print(f"{Fore.LIGHTBLUE_EX}  {item}")
            if wp_includes_loot:
                for item in wp_includes_loot:
                    print(f"{Fore.LIGHTBLUE_EX}  {item}")


        if gowitness_bin and found_misconfigs:
            print("Screenshotting findings with gowitness...")
            out_dir = Path(output_location) / "gowitness-screenshots"
            run_gowitness_file_scan(found_misconfigs, gowitness_bin, out_dir)

    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}{Style.BRIGHT}An error occurred while making the request:{Style.RESET_ALL}")
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)
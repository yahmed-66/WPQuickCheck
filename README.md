# WPQuickCheck - quick WordPress enumeration

---

A quick scanner that checks common misconfigurations for WordPress and screenshots them for use in pentesting reports.

## Quick start:

***Make sure you have GoWitness instaled***

```
git clone https://github.com/yahmed-66/WPQuickCheck
cd WPQuickCheck
pip3 install -r requirements.txt
python3 main.py ~/Desktop
```

## Features

WP Quickcheck scans for the following items and outputs it to a directory of your choosing (defaults to ~):

- `/wp-admin`
- `/wp-login.php`
- `/wp-includes.php`
- `/wp-json`
    - `/wp/v2/users`
- `/wp-config.php`
- `/wp-content`
    - `/themes` 
    - `/plugins`
    - `/uploads`
- `/license.txt`
- `/readme.html`
- User ID enumeration (`/?author=1`)
- `xmlrpc.php` and pingback SSRF

Please make a pull request if you would like to add more features

### Disclaimers

This tool is designed for authorized security testing only. Unauthorized access to computer systems is illegal and punishable by law.

WPQuickCheck is released under the [MIT License](https://opensource.org/license/mit).
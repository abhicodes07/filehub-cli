import asyncio
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RESET = "\033[0m"  # called to return to standard terminal text color

BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
WHITE = "\033[97m"

DOWNLOAD_DIR = Path("filehub_downloads")


def get_repository_url():
    repo_url = sys.argv[1:]
    return repo_url[0]


def check_api_request_limit():
    response = requests.get("https://api.github.com/rate_limit").json()
    rate_remaining = response["rate"]["remaining"]
    rate_used = response["rate"]["used"]
    reset_time = datetime.fromtimestamp(response["rate"]["reset"])
    used_all = False
    if rate_remaining == 0 or rate_used == 60:
        used_all = True
    return {
        "rate_remaining": rate_remaining,
        "rate_used": rate_used,
        "used_all": used_all,
        "reset_time": str(reset_time),
    }


def get_request_url(owner: str, username: str, path: str, dir: str) -> str:
    if dir:
        return f"https://api.github.com/repos/{owner}/{username}/contents/{path}/{dir}?ref=main"
    return f"https://api.github.com/repos/{owner}/{username}/contents/{path}"


def get_repository_content(url: str):
    print("\nFetching repository contents...\n")
    repo_slugs = url.split("/")
    repo_owner = repo_slugs[3]
    repo_name = repo_slugs[4]
    repo_branch = repo_slugs[5:7]
    path = ""

    if len(repo_slugs) > 5:
        path = "/".join(repo_slugs[7:])

    print(f"{BRIGHT_GREEN}[+]{RESET} Repository name: ", end="")
    print(BRIGHT_YELLOW + repo_name + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Owner: ", end="")
    print(BRIGHT_YELLOW + repo_owner + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Branch: ", end="")
    print(BRIGHT_YELLOW + repo_branch[1] + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Path: ", end="")
    print(BRIGHT_YELLOW + path + RESET)

    repo_urls = [
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{path}",
    ]
    response = []
    file_names = []
    file_download_urls = []

    for i, req in enumerate(repo_urls):
        print(BRIGHT_GREEN + f"[{i + 1}]" + RESET + " Fetched URL: ", end="")
        print(BRIGHT_YELLOW + req + RESET)

        response.append(requests.get(req).json())

        if response:
            for res in response:
                for content in res:
                    # fetch files and directories
                    if content["type"] == "file":
                        file_names.append(content["name"])
                        file_download_urls.append(content["download_url"])
                    else:
                        # if the content is dir then create a new requests
                        # to fetch files inside it
                        repo_urls.append(content["url"])
        response.clear()

    return {"file_names": file_names, "download_urls": file_download_urls}


def select_files_fzf(files: dict):
    if not files:
        return
    file_names = "\n".join(files["file_names"])
    try:
        result = subprocess.run(
            [
                "fzf",
                "-m",
                "--border-label",
                "Select Files 📂",
                "--height",
                "~50%",
                "--layout",
                "reverse",
                "--border",
                "--padding",
                "1,2",
                "--header",
                "TAB: mark | ENTER: confirm",
                "--input-label",
                "Input",
                "--exit-0",
            ],
            capture_output=True,
            text=True,
            check=True,
            input=file_names,
        )
    except ChildProcessError:
        print("No file selected, Aborting!")
        return

    return result.stdout


def download_single_file(session: requests.Session, file_name: str, file_url: dict):
    pass


def download_files(content: dict):
    if not content:
        return
    select_files = select_files_fzf(content)
    selected = select_files.split("\n")
    download = []

    for i, file in enumerate(content["file_names"]):
        if selected[i] == file:
            download.append((file, content["download_urls"]))

    print(download)


def main():
    api_status = check_api_request_limit()
    if api_status["used_all"]:
        print(BRIGHT_RED + "Github API rate limit reached!" + RESET)
        print(BRIGHT_RED + "Try again in: " + RESET, end="")
        print(BRIGHT_YELLOW + api_status["reset_time"] + RESET)
        return

    start_time = time.perf_counter()

    repo = get_repository_url()
    repo_content = get_repository_content(repo)
    download_files(repo_content)

    finish_time = time.perf_counter()

    total_time = finish_time - start_time
    print(
        f"\nTotal execution time: {total_time:.2f} seconds. ",
    )

    api_status = check_api_request_limit()
    if not api_status["used_all"]:
        print(
            f"\n{BRIGHT_YELLOW}[!]{RESET} Github API Remaining Rates: {BRIGHT_YELLOW}{api_status['rate_remaining']}{RESET}"
        )
        print(
            f"{BRIGHT_YELLOW}[!]{RESET} Github API Used Rates: {BRIGHT_YELLOW}{api_status['rate_used']}{RESET}"
        )


if __name__ == "__main__":
    main()

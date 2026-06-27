import os
import asyncio
import aiofiles
import subprocess
import sys
import time
import httpx
from datetime import datetime
from pathlib import Path

import requests

RESET = "\033[0m"  # called to return to standard terminal text color

BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
WHITE = "\033[97m"

DOWNLOAD_DIR = Path("filehub_downloads")

# limit download to only 4 cpus
DOWNLOAD_LIMIT = 4
CPU_WORKERS = os.cpu_count()


def get_repository_url() -> str:
    repo_url = sys.argv[1:]
    return repo_url[0]


def check_api_request_limit() -> dict:
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


async def get_repository_content(owner: str, name: str, path: str) -> dict:
    print("\nFetching repository contents...\n")

    repo_urls = [
        f"https://api.github.com/repos/{owner}/{name}/contents/{path}",
    ]

    response = []
    files = {}

    async with httpx.AsyncClient() as client:
        for i, req in enumerate(repo_urls):
            print(BRIGHT_GREEN + f"[{i + 1}]" + RESET + " Fetched URL: ", end="")
            print(BRIGHT_YELLOW + req + RESET)

            res = await client.get(req)
            res.raise_for_status()
            response.append(res.json())

            if response:
                for res in response:
                    for content in res:
                        # fetch files and directories
                        if content["type"] == "file":
                            if content["name"] not in files:
                                files[content["name"]] = {}
                            files[content["name"]]["url"] = content["url"]
                            files[content["name"]]["download_url"] = content[
                                "download_url"
                            ]
                        else:
                            # if the content is dir then create a new requests
                            # to fetch files inside it
                            repo_urls.append(content["url"])
            response.clear()
        print()

    return files


def select_files(files: dict | None = None) -> dict | None:
    if not files:
        return
    file_names = list(files.keys())
    input = "\n".join(file_names)

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
            input=input,
        )
    except ChildProcessError:
        print("No file selected, Aborting!")
        return

    selected_files = result.stdout.split("\n")[:-1]
    selected_file_urls = {}

    print(f"{BRIGHT_GREEN}[+]{RESET} SELECTED FILES:\n")
    for i, selected in enumerate(selected_files, start=1):
        print(f"\t{BRIGHT_GREEN}[{i}]{RESET} {selected}")
        selected_file_urls[selected] = files[selected]["download_url"]
    print()

    return selected_file_urls


async def download_single_file(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    file_name: str,
    download_url: str,
    index: int,
) -> Path:
    download_path = DOWNLOAD_DIR / file_name

    if download_path.exists():
        print(f"{BRIGHT_YELLOW}{file_name}{RESET} already exists!\n")
    else:
        async with semaphore:
            print(f"{BRIGHT_GREEN}[{index + 1}] Downloading {file_name} ...{RESET}")
            ts = int(time.time())
            url = f"{download_url}?ts={ts}"

            response = await client.get(url, timeout=10, follow_redirects=True)
            response.raise_for_status()

            async with aiofiles.open(download_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=512 * 1024):
                    if chunk:
                        await f.write(chunk)

            print(
                f"{BRIGHT_GREEN}[{index + 1}]{RESET} Downloaded {BRIGHT_GREEN}{file_name}{RESET} and saved to {BRIGHT_YELLOW}{download_path}{RESET}\n"
            )

    return download_path


async def download_files(files: dict[str, str] | None = None) -> list[Path] | None:
    if not files:
        return

    # NOTE: LIMIT PROCESSES SPAWN LIMIT IN CPU IN CASE THERE ARE THOURSNADS OF REQUESTS
    dl_semaphore = asyncio.Semaphore(DOWNLOAD_LIMIT)
    async with httpx.AsyncClient() as client:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(download_single_file(client, dl_semaphore, name, url, i))
                for i, (name, url) in enumerate(files.items())
            ]
        file_paths = [task.result() for task in tasks]

    return file_paths


async def main():
    api_status = check_api_request_limit()
    if api_status["used_all"]:
        print(BRIGHT_RED + "Github API rate limit reached!" + RESET)
        print(BRIGHT_RED + "Try again in: " + RESET, end="")
        print(BRIGHT_YELLOW + api_status["reset_time"] + RESET)
        return

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.perf_counter()

    # get repository
    repo = get_repository_url()

    repo_slugs = repo.split("/")
    repo_name = repo_slugs[4]
    repo_owner = repo_slugs[3]
    repo_branch = repo_slugs[6] if len(repo_slugs) > 5 else "main"
    path = ""

    if len(repo_slugs) > 5:
        path = "/".join(repo_slugs[7:])

    print(f"{BRIGHT_GREEN}[+]{RESET} Repository name: ", end="")
    print(BRIGHT_YELLOW + repo_name + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Owner: ", end="")
    print(BRIGHT_YELLOW + repo_owner + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Branch: ", end="")
    print(BRIGHT_YELLOW + repo_branch + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Path: ", end="")
    print(BRIGHT_YELLOW + path + RESET)
    print()

    # fetch repository content
    repo_content = await get_repository_content(repo_owner, repo_name, path)

    file_fetch_start = time.perf_counter()

    # select files
    selected_files = select_files(repo_content)

    download_start = time.perf_counter()

    # download selected files
    file_paths = await download_files(selected_files)

    finish_time = time.perf_counter()

    # calculate execution time
    fetch_time = file_fetch_start - start_time
    select_time = download_start - file_fetch_start
    download_time = finish_time - download_start
    total_time = finish_time - start_time

    print(
        f"\nFetched {len(repo_content)} files in: {BRIGHT_RED}{fetch_time:.2f}{RESET} seconds. {(fetch_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Selected {len(selected_files)} files in: {BRIGHT_RED}{select_time:.2f}{RESET} seconds. {(select_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Downloaded {len(file_paths)} files in: {BRIGHT_RED}{download_time:.2f}{RESET} seconds. {(download_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Total execution time: {BRIGHT_RED}{total_time:.2f}{RESET} seconds. {(total_time / total_time) * 100:.2f}% of total time.",
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
    asyncio.run(main())

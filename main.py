import requests
import subprocess
import sys


def get_repository_url():
    """Take the repository URL as command line argument"""
    repo_url = sys.argv[1:]
    repo_info = repo_url[0].split("/")
    return repo_info


def get_repository_content():
    """Fetch the repository contents and metadata"""
    repo = get_repository_url()
    repo_owner = repo[3]
    repo_name = repo[4]
    path = ""
    if len(repo) > 5:
        raw_path = "/".join(repo[4:])
        path = "/" + raw_path + "/"

    repo_content_raw = requests.get(
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{path}"
    )
    repo_content_json = repo_content_raw.json()
    return repo_content_json


def choose_file(file_list, prompt):
    """Display list of files in fzf viewer."""
    if not file_list:
        return None

    try:
        result = subprocess.run(
            [
                "fzf",
                "--prompt",
                prompt,
                "--height",
                "~50%",
                "--layout",
                "reverse",
                "--border",
                "--exit-0",
            ],
            capture_output=True,
            text=True,
            check=True,
            input=file_list,
        )
    except ChildProcessError:
        print("No file selected, Aborting!")
        return None

    return result


def fetch_files(repo_content):
    """
    Get files and its contents

    repo_content: list
    """
    if not repo_content:
        return None

    files = []
    dirs = []

    for content in repo_content:
        if content["type"] == "file":
            files.append(content["name"])
        else:
            dirs.append(content["name"])
        # files.append(content["name"])
        # file_types.append((content["name"], content["type"]))

    print(files)
    print(dirs)


def download_file(file_name, repo_content):
    if not file_name:
        return None

    file = file_name.split("\n")
    for item in repo_content:
        if item["name"] == file[0]:
            print("found")
        else:
            print("not found")


def main():
    content = get_repository_content()
    fetch_files(content)


if __name__ == "__main__":
    main()

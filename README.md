## Todos

- [ ] Convert the program into CLI.
- [x] Use `click` or `argparse` for better CLI tool management
- [ ] Add file download progress bar
- [ ] Download path feature
- [x] Specific branch feature
- [ ] `fzf` alternative if it not installed
- [x] preserve the path of the file, download files in the respective directory structure
- [x] download files in the directory same as repository name instea of `filehub_downloads`
- [x] handle if the repository URL is not provided.
- [x] check if the provided url is a Github url
- [ ] handle if github repo doesn't exits
- [ ] if files from different branches are downloaded then download them seperately in their respective branch named directory
- [ ] if the file github url is provided, download it directly
- [ ] handle the branch name if it's provided in the URL
- [ ] create a flag for whether to preserve the repository directory structure
- [ ] handle program cancellation using `CTRL+C`
- [ ] handle root directory cleanup if exited unexpectedly
- [ ] check internet connectivity
- [ ] handle if the default branch is `master` or anythin else
- [ ] maybe get a branch
- [ ] user authentication for more api requests
- [ ] check if branch exits or not

> [!ERROR] NOTE
> if in case branch name looks like a path such as `feat/jobdori-122b-doctor-broad-cwd` then it might cause an error as we cannot find the branch in the URL and it might get included in the path segment of urlparse. To avoid this, loop over the path segements and make api calls until we get the 200 status and find the right branch

```
-b : branch
-p : path
```

## Resources

- [Progress bar](https://stackoverflow.com/questions/6415402/creating-a-progress-bar-in-a-cli-application)
- [Click module](https://realpython.com/python-click/#creating-command-line-interfaces-with-click-and-python)
- [Packaging CLI Tool](https://packaging.python.org/en/latest/guides/creating-command-line-tools/)

## Todos

- [ ] Convert the program into CLI.
- [x] Use `click` or `argparse` for better CLI tool management
- [ ] Add file download progress bar
- [ ] Download path feature
- [x] Specific branch feature
- [ ] `fzf` alternative if it's not installed
- [x] preserve the path of the file, download files in the respective directory structure
- [x] download files in the directory same as repository name instea of `filehub_downloads`
- [x] handle if the repository URL is not provided.
- [x] check if the provided url is a Github url
- [ ] handle if github repo doesn't exits
- [ ] if files from different branches are downloaded then download them seperately in their respective branch named directory

```
-b : branch
-p : path
```

## Resources

- [Progress bar](https://stackoverflow.com/questions/6415402/creating-a-progress-bar-in-a-cli-application)
- [Click module](https://realpython.com/python-click/#creating-command-line-interfaces-with-click-and-python)
- [Packaging CLI Tool](https://packaging.python.org/en/latest/guides/creating-command-line-tools/)

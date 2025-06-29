# Contributing to PyPowerwall

Thank you for your interest in contributing to PyPowerwall! We welcome contributions that improve the project and make it more useful for everyone. Please read the following guidelines to help us maintain a high-quality, maintainable, and collaborative codebase.

## General Guidelines

- **Keep it Modular:**  
  Structure your code in small, focused modules and functions. Avoid monolithic files or classes. This makes the code easier to read, test, and maintain.

- **Small Pull Requests:**  
  Submit small, focused pull requests (PRs) that address a single issue or feature. This makes it easier for reviewers to evaluate and approve your changes quickly.

- **Simplicity:**  
  Strive for simplicity in your code and design. Avoid unnecessary complexity. Write code that is easy to understand and modify by others.

- **Readability:**  
  Use clear, descriptive names for variables, functions, and classes. Add comments where necessary, especially for non-obvious logic.

- **Testing:**  
  We recommend that you thoroughly test your changes before submitting a PR. While unit tests are not strictly required, contributions that include appropriate unit tests are highly appreciated and will receive extra consideration. Make sure all existing tests pass before submitting your PR. PRs without tests may still be accepted if they are well-tested and documented.

- **Release Notes:**  
  For any user-facing changes, please add a summary to the `RELEASE.md` file describing what changed and why.

## Setting Up Your Development Environment

- Clone the repository:
  ```
  git clone https://github.com/jasonacox/pypowerwall.git
  cd pypowerwall
  ```
- (Optional) Create and activate a virtual environment:
  ```
  python3 -m venv venv
  source venv/bin/activate
  ```
- Install runtime dependencies (required to run the package):
  ```
  pip install -r requirements.txt
  ```
- (For contributors running tests) Install test dependencies (required to execute unit tests):
  ```
  pip install -r test_requirements.txt
  ```

## Dependency Files: requirements.txt vs. test_requirements.txt

- `requirements.txt` lists the dependencies required to run the PyPowerwall package itself. Install these to use the library or run the main application.
- `test_requirements.txt` lists additional dependencies needed only for running the unit tests (e.g., pytest, mock libraries). Install these if you plan to run or write tests:
  ```
  pip install -r test_requirements.txt
  ```
- You typically need both files for full development and testing, but end users only need `requirements.txt`.

## How to Run Tests

- **Note:** The following applies to the Python library only. The proxy server and other tools have their own testing and validation processes.
- Tests are located in the `pypowerwall/tests/` directory.
- Before running tests, ensure you have installed both `requirements.txt` and `test_requirements.txt` dependencies (see above).
- Run all tests with:
  ```
  pytest
  ```
- If your contribution requires hardware or external services, please use mocks or document how to test your changes.

## How to Contribute

1. **Fork the Repository**  
   Create your own fork of the project and clone it locally.

2. **Create a Branch**  
   Create a new branch for your feature or bugfix:
   ```
   git checkout -b feature/my-new-feature
   ```

3. **Make Your Changes**  
   Keep your changes focused and modular. Update or add tests as needed.

4. **Test Your Changes**  
   Run all tests locally to ensure nothing is broken:
   ```
   pytest
   ```

5. **Update Release Notes**  
   Add a brief summary of your change to `RELEASE.md`.

6. **Submit a Pull Request**  
   Push your branch to your fork and open a pull request against the main repository. Provide a clear description of your changes and reference any related issues.

## Issues vs. Discussions

- **Issues** are for reporting bugs, requesting features, or tracking specific tasks that require action or resolution. Use an issue when you have a concrete problem, bug, or enhancement to propose. Issues should be closed when the problem is resolved, the feature is implemented, or the task is complete.

- **Discussions** are for open-ended conversations, brainstorming, questions, or general feedback that may not require direct action or a code change. Use a discussion when you want to ask for advice, share ideas, or start a broader conversation. Discussions can be closed when the conversation has naturally concluded, a consensus is reached, or the topic is no longer active.

> These are guidelines, not strict rules. If you're unsure, start a discussion—maintainers can help move it to an issue if needed.

## Flexibility and Exceptions

While the guidelines above are generally adhered to, the maintainers are not strict rules lawyers. We value thoughtful contributions and are always open to reasonable exceptions or nuanced cases. If you have a good reason to diverge from a guideline, or if your situation doesn't fit neatly into the rules, please start a conversation—collaboration and flexibility are encouraged.

## Branch Naming and Commit Messages

- Use descriptive branch names, e.g., `fix/issue-123-description` or `feature/add-new-api`.
- Write clear, concise commit messages that explain the "why" behind your changes.

## Code Style

- Follow [PEP 8](https://pep8.org/) for Python code style.
- Use [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) for docstrings and comments.
- Use type hints where appropriate.

## Reviewing and Approval

- PRs will be reviewed for clarity, modularity, simplicity, and test coverage.
- Please be responsive to feedback and willing to make changes as requested.

## Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

## Licensing

By contributing, you agree that your contributions will be licensed under the same license as the rest of the project (see [`LICENSE`](LICENSE)).

## Versioning Policy

This project follows [Semantic Versioning](https://semver.org/). Version numbers are in the format MAJOR.MINOR.PATCH:

- **MAJOR** version when you make incompatible API changes,
- **MINOR** version when you add functionality in a backwards-compatible manner, and
- **PATCH** version when you make backwards-compatible bug fixes.

Please update the version number appropriately in your pull request if your change warrants it, and describe the change in `RELEASE.md`.

## Relationship to Powerwall-Dashboard

PyPowerwall focuses on providing core Python functionality to access Tesla Powerwall and Tesla Solar systems. This repository contains the Python library and proxy server for programmatic and easy access to Powerwall data and control features.

The [Powerwall-Dashboard](https://github.com/jasonacox/powerwall-dashboard) project provides a Grafana dashboard for visualizing Powerwall data. It uses PyPowerwall to collect data, stores it in InfluxDB, and displays it in Grafana. Powerwall-Dashboard also manages the container stack needed for the dashboard setup.

Since PyPowerwall and [Powerwall-Dashboard](https://github.com/jasonacox/powerwall-dashboard) work closely together, many features, bugs, and enhancements may affect both projects. Please mention this in your issue or discussion if applicable. Maintainers may move or cross-reference issues between repositories as needed.

**Where to contribute:**
- PyPowerwall: Changes related to the Python library, API, or proxy server (e.g., new endpoints, bug fixes, data collection improvements)
- Powerwall-Dashboard: Changes related to dashboard setup, Grafana dashboards, InfluxDB configuration, or container stack management. Additionally, users are encouraged to start or join discussions about the Powerwall system itself or Powerwall Firmware updates (including problems) to that project first.
- Not sure? Start a discussion in either repository - maintainers will help direct it appropriately
- When submitting PRs or issues, check for and reference any related items in the sister project
- Issues may move between projects as needed; cross-project collaboration is encouraged

## Platform and Compatibility Notes

- **Backward Compatibility:**
  We strive to maintain backward compatibility and avoid breaking existing installations whenever possible. If your contribution introduces a breaking change, please clearly document it and discuss with the maintainers before submitting your PR.

- **Multi-Platform Support:**
  PyPowerwall aims to support a wide range of platforms, including Raspberry Pi, Linux, Windows, macOS, and appliance-based compute platforms (such as Synology). Contributors are encouraged to consider cross-platform compatibility and, where possible, test changes on multiple platforms. Please note any platform-specific considerations or limitations in your PR description.

## Questions

If you have any questions or need clarification, feel free to open an issue or start a discussion.

Thank you for helping make PyPowerwall better!

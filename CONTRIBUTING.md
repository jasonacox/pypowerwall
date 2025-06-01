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
  All new features and bug fixes should include appropriate unit tests. Make sure all tests pass before submitting your PR. PRs without tests may not be accepted.

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
- Install dependencies:
  ```
  pip install -r requirements.txt
  ```

## How to Run Tests

- Tests are located in the `pypowerwall/tests/` directory.
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

## Issue Reporting and Feature Requests

If you find a bug or have a feature request, please [open an issue](https://github.com/jasonacox/pypowerwall/issues) first to discuss your idea before submitting a pull request.

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

By contributing, you agree that your contributions will be licensed under the same license as the rest of the project (see `LICENSE`).

## Questions

If you have any questions or need clarification, feel free to open an issue or start a discussion.

Thank you for helping make PyPowerwall better!

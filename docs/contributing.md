# 🤝 Contributing to Meta App Chatbot

Thank you for your interest in contributing to the Meta App Chatbot! We welcome all contributions, including bug reports, feature requests, documentation improvements, and code changes.

## 🚀 How to Contribute

### 1. 🐛 Reporting Bugs

If you find a bug, please create a new issue on GitHub. Include:

- A clear, descriptive title.
- Steps to reproduce the bug.
- Actual vs. expected behavior.
- Any relevant logs or screenshots.

### 2. ✨ Feature Requests

Have an idea to make the chatbot better? Open an issue and describe:

- The problem it solves.
- How you envision it working.

### 3. 🛠️ Code Contributions

1. Fork the repository and clone it locally.
2. **Install development dependencies**:

    ```bash
    uv sync --dev
    ```

3. Create a new branch for your feature or fix.
4. Write code and tests.
5. **Run lints and tests** before submitting:

    ```bash
    ruff check .
    pytest
    ```

6. Push to your fork and **open a Pull Request** to the `main` branch.

## 📜 Code Style

We use **Ruff** for linting and formatting. Ensure your code follows the project's standards by running `ruff check . --fix`.

## 📄 License

By contributing, you agree that your contributions will be licensed under the project's **MIT License**.

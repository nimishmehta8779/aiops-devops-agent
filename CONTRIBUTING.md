# Contributing to AI DevOps Agent

Thank you for your interest in contributing to the AI DevOps Agent! This document provides guidelines and instructions for contributing.

## 🤝 How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (AWS region, Terraform version, etc.)
- Relevant logs or error messages

### Suggesting Enhancements

We welcome feature requests! Please create an issue with:
- Clear description of the enhancement
- Use case and benefits
- Proposed implementation (if you have ideas)
- Any potential drawbacks or considerations

### Pull Requests

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow the existing code style
   - Add tests for new functionality
   - Update documentation as needed

4. **Test your changes**
   ```bash
   cd demos
   ./quick_test.sh
   ```

5. **Commit your changes**
   ```bash
   git commit -m "feat: add amazing feature"
   ```
   
   Use conventional commits:
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation changes
   - `test:` adding or updating tests
   - `refactor:` code refactoring
   - `chore:` maintenance tasks

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request**
   - Provide a clear description
   - Reference any related issues
   - Include screenshots if applicable

## 📋 Development Guidelines

### Code Style

**Python**
- Follow PEP 8
- Use type hints where possible
- Add docstrings for functions and classes
- Keep functions focused and small

**Terraform**
- Use consistent formatting (`terraform fmt`)
- Add comments for complex logic
- Use variables for configurable values
- Follow AWS naming conventions

### Testing

All changes should include tests:
- Unit tests for Lambda functions
- Integration tests for Terraform modules
- End-to-end tests for complete workflows

Run tests before submitting:
```bash
cd demos
./quick_test.sh          # Quick validation
./automated_test_recovery.sh  # Full test suite
```

### Documentation

Update documentation for:
- New features
- Changed behavior
- New configuration options
- Breaking changes

Documentation files:
- `README.md` - Main project overview
- `docs/DEPLOYMENT_GUIDE.md` - Deployment instructions
- `docs/ARCHITECTURE_COMPARISON.md` - Architecture details
- Inline code comments

## 🏗️ Project Structure

```
aiops-devops-agent/
├── 01-base-infra/          # Base infrastructure
├── 02-app-infra/           # Application infrastructure
├── 03-agent-lambdas/       # Agent Lambda functions
├── 04-bedrock-agent/       # Bedrock configuration
├── 05-orchestration/       # Main orchestrator
├── 06-log-analyzer/        # Log analysis Lambda
├── demos/                  # Demo scripts
├── docs/                   # Documentation
├── README.md
├── LICENSE
└── CONTRIBUTING.md
```

## 🧪 Testing Checklist

Before submitting a PR, ensure:
- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] New tests added for new functionality
- [ ] Documentation updated
- [ ] No sensitive data in commits
- [ ] Terraform validates (`terraform validate`)
- [ ] Python lints cleanly (`pylint`, `flake8`)

## 🔒 Security

- Never commit AWS credentials
- Use AWS Secrets Manager for sensitive data
- Follow least-privilege IAM principles
- Report security vulnerabilities privately

## 📝 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 💬 Communication

- **Issues**: For bugs and feature requests
- **Pull Requests**: For code contributions
- **Discussions**: For questions and ideas

## 🙏 Thank You!

Your contributions help make this project better for everyone!

## 📚 Resources

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Terraform Best Practices](https://www.terraform.io/docs/cloud/guides/recommended-practices/index.html)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Python PEP 8 Style Guide](https://www.python.org/dev/peps/pep-0008/)

## 🎯 Good First Issues

Look for issues labeled `good-first-issue` - these are great for new contributors!

## 🌟 Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- Project documentation

---

**Happy Contributing!** 🚀

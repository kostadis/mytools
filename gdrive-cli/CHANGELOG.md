# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-07

### Added
- Full implementation of Google Drive and OneDrive functionality
- All commands: scan, dupes, move, trash for both services
- Comprehensive unit tests for all functionality
- Complete documentation in README.md
- Example usage scripts in examples/ directory
- GitHub Actions CI/CD pipeline
- Version flag in CLI (`gdrive-cli --version`)

### Changed
- Unified authentication system using `~/.config/gdrive-cli/`
- Consistent JSONL output format across services
- Improved error handling and user feedback

### Removed
- Outdated COMPLETION_PLAN.md (was inaccurate)

### Security
- Secure authentication flows with OAuth2
- Token caching with expiration handling
- Rate limiting and retry logic for API calls

### Performance
- Efficient pagination for large drives
- Parallel processing where possible
- Optimized duplicate detection algorithm

### Documentation
- Comprehensive README with setup and usage instructions
- Example scripts demonstrating real-world use cases
- Clear error messages and troubleshooting guide

### Testing
- Unit tests for all functions
- Integration tests for authentication flows
- Code coverage reporting

### CI/CD
- Automated testing on Linux, macOS, and Windows
- Code quality checks with clippy and fmt
- Automated release generation with checksums
- Binary distribution for all platforms

### Examples
- duplicate_cleanup.sh - Script to identify and clean up duplicate files
- file_organization.sh - Script to organize files by type and date

## [0.1.0] - 2026-06-07 (Initial)

Initial release with basic functionality.

### Added
- Google Drive scan and dupes commands
- Basic authentication system
- Command-line interface

### Changed
- Initial structure and organization

### Removed
- None

### Security
- Initial OAuth2 implementation

### Performance
- Basic pagination for large drives

### Documentation
- Basic README

### Testing
- Basic unit tests for Google Drive

### CI/CD
- Initial CI setup

### Examples
- None

### Notes
- This project has been significantly enhanced since the initial release.
- The current version (1.0.0) is a complete implementation with all features.
- The initial 0.1.0 release was incomplete and has been superseded.
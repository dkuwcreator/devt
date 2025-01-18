# Dev-Tools

Sharing Development Tools made easy

## **What is `devt`?**

`devt` is a command-line interface (CLI) tool that functions like a package manager, designed to streamline the installation, configuration, and management of development tools for teams and organizations. It automates tasks such as installing tools, resolving dependencies, and running scripts in alignment with company policies.

### **The Problem**

In a professional environment, developers often rely on a wide range of tools—linters, formatters, testing frameworks, Docker, Kubernetes, Terraform, Visual Studio Code, and more. Managing these tools across various projects and setups can be a complex and time-consuming process, particularly when:

- Team members have different system configurations.
- Company policies enforce specific tool versions or configurations.
- Admin rights or security protocols limit installation options.

This often leads to duplicated effort and inconsistencies across teams.

### **The Solution: `devt`**

`devt` addresses these challenges by providing a centralized way to manage development tools. It allows teams to define required tools as simple "packages" that can be easily shared and reused. For example:

- A developer can create a package that includes installation scripts, configuration files, and dependencies for a specific tool.
- The package can then be shared across the team, ensuring consistent setups and configurations.
- This eliminates the need for each developer to figure out installation and configuration steps individually.

By using `devt`, teams can:

- **Save time**: Avoid repetitive setup tasks.
- **Reduce errors**: Ensure tools are installed and configured according to company standards.
- **Increase consistency**: Provide reliable and uniform setups across projects and team members.

Whether it’s setting up linters or handling complex tools like Kubernetes, `devt` simplifies the process, empowering developers to focus on coding rather than configuration.

---

### **How `nndev` Works**

`nndev` operates by maintaining a central directory on the user's computer where all tool packages are stored. Users can add packages by cloning them from Git repositories, which can be automatically synced or notify users of changes. Additionally, users have the flexibility to add their own packages locally.

1. **Repository Structure**:

For example, a company might have a shared `.utils` repository containing tool packages for Git, Node.js, Python, and more. This looks like:

- The repository contains a `root` directory where all tools are stored.
- Each tool is defined in a subdirectory which forms a "package".
- Each tool package includes a `manifest.json` file and optionally other files like scripts or configuration files or templates.

Example Structure:

   ```
   utilities_repo/
    ├── python/
    │   ├── manifest.json
    │   ├── scripts/
    │   |   ├── install.sh
    │   |   └── update.sh
    |   └── certs/
    |       └── company_cert.pem
    ├── nodejs/
    │   ├── manifest.json
    │   └── scripts/
    │       ├── install.sh
    │       └── update.sh
    └── git/
        ├── manifest.json
        └── scripts/
            ├── set.sh
            └── update.sh
   ```

2. **Manifest File (`manifest.json`)**:

   - Each tool’s manifest file describes its name, dependencies, and available scripts.

   Example `manifest.json` for the `azd` tool:

   ```json
   {
     "name": "Azure Developer CLI",
     "description": "Azure Developer CLI is a command-line tool providing a great experience for managing Azure resources.",
     "dependencies": {
       "posix": {},
       "windows": {
         "winget": ">=1.9.25200"
       }
     },
     "scripts": {
       "posix": {
         "install": "scripts/install.sh",
         "uninstall": "scripts/uninstall.sh",
         "upgrade": "scripts/install.sh"
       },
       "windows": {
         "install": "winget install -e --id Microsoft.Azd --custom '/passive /qn'",
         "uninstall": "winget uninstall -n Microsoft.Azd",
         "upgrade": "winget upgrade -n Microsoft.Azd"
       },
    "version": "azd version",
       "test": "azd version"
     }
   }
   ```

   Example `manifest.json` for the `az` tool:

   ```json
   {
     "name": "Azure CLI",
     "description": "Azure CLI is a command-line tool providing a great experience for managing Azure resources.",
     "dependencies": {
       "python": ">=3.6"
     },
     "scripts": {
       "install": "pip install azure-cli",
       "uninstall": "pip uninstall azure-cli",
       "upgrade": "pip install --upgrade azure-cli",
         "version": "az --version",
       "test": "az --version"
     }
   }
   ```


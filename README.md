# Dev-Tools

### Sharing Development Tools Made Easy

## **What is DevT?**

`devt` is a command-line interface (CLI) tool that acts as a package manager to simplify the installation, configuration, and management of development tools for teams and organizations. It automates tasks such as:

- Installing tools
- Resolving dependencies
- Running scripts per company policies

### **Problem and Solution**

Modern developers rely on various tools—linters, formatters, testing frameworks, Docker, Kubernetes, Terraform, Visual Studio Code, and more. Managing these tools across projects and setups can be challenging due to:

- Diverse system configurations among team members
- Company policies requiring specific tool versions or configurations
- Admin rights or security restrictions complicating installations

This often leads to duplicated effort and inconsistencies across teams. For instance, developers might spend hours resolving dependency conflicts when setting up a linter or formatter manually, only to discover later that other team members are using different configurations. These mismatches can lead to issues like differing code styles, missed bugs, or wasted time troubleshooting discrepancies.

`devt` addresses these challenges by providing a centralized way to manage development tools. Teams can define required tools as simple "packages" that are easily shared and reused. Here's how it works:

- Developers create packages that include installation scripts, configuration files, and dependencies for specific tools.
- These packages are shared across the team, ensuring consistent setups and configurations.
- This eliminates the need for developers to individually figure out installation and configuration steps.

**Key Benefits of DevT:**

- **Time-Saving**: Skip repetitive setup tasks.
- **Error Reduction**: Ensure compliance with company standards.
- **Consistency**: Maintain uniform setups across projects and team members.

From basic linters to complex tools like Kubernetes, `devt` enables developers to focus on coding, not configuration. For instance, developers might spend hours resolving dependency conflicts when setting up a linter or formatter manually, only to discover later that other team members are using different configurations. These mismatches can lead to issues like differing code styles, missed bugs, or wasted time troubleshooting discrepancies.

## **Using DevT**

`devt` operates by maintaining a central directory on the user's computer where all tool packages are stored. Users can add packages by cloning them from Git repositories, which can be automatically synced or notify users of changes. Additionally, users can add their own packages locally.

### Tool Packages in `devt`

Tool packages are the core of `devt`. They encapsulate all scripts, dependencies, and configurations needed to install, configure, and run a development tool. By organizing tools into standardized packages, `devt` enables developers to share, manage, and automate tool usage effectively across teams and environments.

### **Structure of a Tool Package**

Each tool package resides in its own directory and must include the following components. These components are essential for defining the structure and behavior of the tool package, ensuring that all necessary scripts and resources are organized in a predictable and reusable format.

1. **`manifest.json`** (mandatory): A configuration file describing the tool, its dependencies, and associated scripts.
2. **Scripts** (optional): Executable files for installation, configuration, or other tasks.
3. **Resources** (optional): Supporting files such as certificates, templates, or other required assets.

**Example Directory Structure:**

```
<tool_package_name>/
├── manifest.json
├── scripts/
│   ├── install.sh
│   ├── upgrade.sh
│   └── uninstall.sh
└── resources/
    └── company_cert.pem
```

### **Manifest File**

The `manifest.json` specifies the following:

- **Name and Description**: Metadata about the tool.
- **Dependencies**: Other tools or system requirements.
- **Scripts**: Paths to scripts for various operations (e.g., install, upgrade, uninstall, test, version).
- **Path Resolution**: Mechanisms for resolving paths to scripts and resources.

**Example `manifest.json`:**

```json
{
  "name": "Example Tool",
  "description": "A sample tool with scripts for installation and updates.", # Optional
  "command": "tool-cli",
  "base_dir": ".", # Optional
  "dependencies": {
    "python": ">=3.6",
    "pip": ">=20.0"
  }, # Optional
  "scripts": {
    "install": "pip install example-tool", # Mandatory
    "uninstall": "pip uninstall example-tool", # Mandatory
    "upgrade": "pip install --upgrade example-tool", # Mandatory
    "version": "tool-cli --version", # Mandatory
    "test": "tool-cli --test" # Mandatory
  }
}
```

Mandatory fields in the `manifest.json` include `name`, `dependencies`, and `scripts`. Dependencies can specify version constraints for tools or libraries required by the package.

### **Key Features of Tool Packages**

#### 1. **Cross-Platform Support**

`devt` supports OS-specific scripts and dependencies, allowing the same tool package to adapt to Windows, macOS, and Linux environments.

**Example Manifest for Cross-Platform Scripts:**

```json
{
  "name": "Cross-Platform Tool",
  "command": "tool-cli",
  "scripts": {
    "windows": {
      "install": "./scripts/install.ps1",
      "upgrade": "./scripts/upgrade.ps1"
    },
    "posix": {
      "upgrade": "./scripts/upgrade.sh"
    },
    "install": "./scripts/install.sh",
    "uninstall": "./scripts/uninstall.sh",
    "version": "tool-cli --version",
    "test": "tool-cli --test"
  }
}
```

On Windows, `devt` executes the `install.ps1` script for installation and the `upgrade.ps1` script for upgrades. On macOS and Linux, it runs the `install.sh` and `upgrade.sh` scripts, respectively. The `test` script is common to all platforms.

```json
{
  "install": "./scripts/install.ps1",
  "update": "./scripts/update.ps1",
  "test": "tool-cli --test"
}
```

#### 2. **Dependency Management**

Tool packages can declare dependencies on other tools or libraries:

```json
"dependencies": {
  "python": ">=3.6",
  "pip": ">=20.0"
}
```

Dependencies can also be OS-specific:

```json
"dependencies": {
  "windows": {
    "winget": ">=1.9.25200"
  },
  "posix": {
    "apt": ">=2.2.4"
  }
}
```

#### 3. **Path Resolution**

Relative paths in `manifest.json` are resolved based on the directory containing the manifest. The `base_dir` field can customize this behavior.

### **Central Tools Repository**

A company could maintain a shared `utilities_repo` repository housing packages for tools like Git, Azure CLI, and Python. Example structure:

```
utilities_repo/
├── python/
│   ├── manifest.json
│   ├── scripts/
│   │   ├── install.sh
│   │   └── update.sh
│   └── certs/
│       └── company_cert.pem
├── az/
│   └── manifest.json
└── git/
    ├── manifest.json
    └── scripts/
        ├── set.sh
        └── update.sh
```

## **Core Functionality of DevT?**

### **Managing Tool Packages**

To add the company’s `utilities_repo` to the local `devt` directory:

```bash
devt add https://example.com/utilities_repo
```

This command clones the repository and syncs it locally. Alternatively, add a local directory: This option is useful when you have custom or experimental tools that are not yet part of a shared repository or when you prefer faster access and modifications without relying on a remote server.

```bash
devt add /path/to/local/package
```

`devt` manages tools via a `registry.json` file. To view available tools:

```bash
devt list
```

Other commands:

- `devt remove <tool>`: Removes a tool package.
- `devt sync`: Syncs with remote repositories.

### **Script Execution**

Next to the basic functionality of sharing tools, `devt` offers another core feature to enhance the developer experience, which is using tools on a daily basis or in a project-specific context.

Once the repository is added, you can make use of the tools by running scripts defined in the tool packages. For example, to install the Azure CLI tool, you would run:

```bash
devt install az
```

In this case, the command executes the `install` script specified in the `manifest.json` file for the `az` package. For example, this script might run the equivalent of:

```bash
pip install azure-cli
```

`devt` intelligently resolves all underlying operating system dependencies and executes the appropriate script for your environment. This eliminates the need for developers to worry about platform-specific commands or configurations.

The standard commands for script execution include:

- `devt install <tool>`: Installs the specified tool package.
- `devt uninstall <tool>`: Uninstalls the specified tool package.
- `devt upgrade <tool>`: Upgrades the specified tool package.
- `devt version <tool>`: Displays the version of the specified tool package.
- `devt test <tool>`: Runs the test script for the specified tool package.

### **Running Tools Directly**

With `devt`, you can execute any tool directly from the command line by running:

```bash
devt do <tool> <script>
```

For example, to execute the `deploy` script in the `azd` package, you would run:

```bash
devt do azd deploy
```

`devt` intelligently resolves all underlying operating system dependencies and executes the appropriate script for your environment. This eliminates the need for developers to worry about platform-specific commands or configurations.

For instance:

- On Windows, `devt` might execute a PowerShell script (`set.ps1`).
- On macOS or Linux, it might execute a Bash script (`set.sh`).

This flexibility ensures that teams using multiple operating systems can share tools without additional effort.

Run scripts directly using:

```bash
devt install <tool>
```

`devt` resolves dependencies and executes platform-specific scripts.

Standard commands:

- `devt install <tool>`
- `devt uninstall <tool>`
- `devt upgrade <tool>`
- `devt version <tool>`
- `devt test <tool>`

### **Project-Specific Context**

Projects can define tools and scripts in `devt.json`:

```json
{
  "tools": {
    "azd": "1.5.0",
    "checkov": "2.0.0",
    "terraform": "1.0.11"
  },
  "scripts": {
    "test": "terraform init && terraform validate && checkov -d .",
    "deploy": "azd up",
    "destroy": "azd down"
  }
}
```

Run scripts with:

```bash
devt run test
```

Other commands:

- `devt init`: Initializes a project with `devt.json`.

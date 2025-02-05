# Dev-Tools

### Sharing Development Tools Made Easy

## What is DevT?

**DevT** is a command-line interface (CLI) tool that acts as a package manager for development tools, simplifying the installation, configuration, and management of these tools across teams and organizations. It automates tasks such as:

- Installing tools
- Resolving dependencies
- Running scripts according to company policies

## The Problem and Our Solution

Modern developers rely on a wide range of tools—linters, formatters, testing frameworks, Docker, Kubernetes, Terraform, Visual Studio Code, and more. Managing these tools across diverse projects and system configurations is challenging because:

- Team members often work on different operating systems.
- Company policies require specific tool versions or configurations.
- Administrative rights or security restrictions can complicate installations.

This leads to duplicated efforts, inconsistent setups, and wasted time troubleshooting dependency conflicts. **DevT** addresses these challenges by providing a centralized way to manage development tools through simple, shareable packages.

## Key Benefits

- **Time-Saving:** Automate repetitive setup tasks.
- **Error Reduction:** Ensure all team members use standardized, approved configurations.
- **Consistency:** Maintain uniform environments across projects and developers.

## How DevT Works

DevT maintains a central registry (a JSON file) that tracks all tool packages installed by the user. There are two levels of configuration:

1. **User-Level Registry:** Global tools available to all projects.
2. **Workspace-Level Registry:** Project-specific tools and configurations, merged from a `workspace.json` file located in the project’s root directory.

### Workflow

1. **Adding Tools:**

- **Repository Tools:**  
  Clone or update remote repositories containing tool packages using:
  ```bash
  devt add https://github.com/your-org/your-tool-repo.git
  ```
  This command clones the repository into a local directory (e.g. under `.registry/repos/`) and scans it for tool packages.
- **Local Tools:**  
  Import local tool packages (or a collection of packages) into the registry:
  ```bash
  devt local import /path/to/local/tool-package
  ```
  Tools are grouped automatically—if you import a folder containing multiple tools, the group is set based on the folder name unless overridden by a `--group` option.

2. **Managing Tools:**  
   Use commands such as:

   - `devt list` – List all available tools.
   - `devt remove <tool>` – Remove a specific tool.
   - `devt sync` – Synchronize all repository-based tools with their remote sources.

3. **Executing Scripts:**  
   The **core feature** of DevT is to execute predefined scripts from tool packages. Each tool package contains a `manifest.json` defining metadata and a set of scripts for operations like installation, upgrade, or testing.

   - **Standard Commands:**

     - `devt install <tool>` – Executes the `install` script for the tool.
     - `devt uninstall <tool>` – Executes the `uninstall` script.
     - `devt upgrade <tool>` – Executes the `upgrade` script.
     - `devt version <tool>` – Displays the tool’s version.
     - `devt test <tool>` – Runs the tool’s test script.

   - **Direct Script Execution:**  
     Use the `do` command to run any script defined in a tool’s manifest:
     ```bash
     devt do <tool> <script> [arguments]
     ```
     For example:
     ```bash
     devt do azd deploy
     ```
     **DevT** first looks up the tool in the workspace registry (project-specific) and falls back to the user registry if needed—no need to specify `--workspace`. It automatically resolves the correct script based on your operating system (e.g. PowerShell on Windows, Bash on POSIX systems) and executes it in the appropriate working directory. If auto-sync is enabled for the tool, the repository is updated before running the script.

## Tool Package Structure

Tool packages encapsulate all the scripts, dependencies, and configurations needed for a development tool. This standardization allows teams to share and reuse tool packages reliably.

### Mandatory Components

1. **`manifest.json`:**  
   A configuration file that includes:

   - **Name and Description:** Metadata about the tool.
   - **Command:** A unique identifier used in the registry and CLI (e.g. `testy`).
   - **Dependencies:** Version constraints for required tools/libraries.
   - **Scripts:** A set of commands for key operations (install, uninstall, upgrade, version, test).
   - **base_dir (optional):** A custom base directory for resolving paths.

2. **Scripts (optional):**  
   Executable files that perform installation, updates, or tests.

3. **Resources (optional):**  
   Supporting files such as certificates or configuration templates.

### Example `manifest.json`

```json
{
  "name": "Testy the Test",
  "description": "This is a testy function.",
  "command": "testy",
  "base_dir": ".",
  "dependencies": {
    "python": "^3.9.0",
    "pip": "^21.0.0"
  },
  "scripts": {
    "windows": {
      "install": "echo \"Testy is installed on Windows.\"",
      "update": "echo \"Testy is updated on Windows.\""
    },
    "posix": {
      "update": "echo \"Testy is updated on POSIX.\""
    },
    "install": "echo \"Testy is installed on all platforms.\"",
    "uninstall": "echo \"Testy is uninstalled on all platforms.\"",
    "version": "echo \"Testy is versioned on all platforms.\"",
    "test": "echo \"Testy is tested on all platforms.\""
  }
}
```

### Directory Layout

Imported local packages are stored under a grouping structure, for example:

```
.registry/
└── tools/
    └── default/
         └── test_tool/
              └── manifest.json
```

Repositories are stored under:

```
.registry/
└── repos/
    └── devt-tools/
         └── (various tool package directories)
```

## Project-Specific Context

Projects can have their own configuration defined in a `workspace.json` file located at the project root. This file allows you to specify project-specific tools and scripts. When present, **DevT** automatically adds the contents of `workspace.json` to the workspace registry under the key `"workspace"`.

### Example `workspace.json`

```json
{
  "tools": {},
  "scripts": {
    "test": "terraform init && terraform validate && checkov -d .",
    "deploy": "azd up",
    "destroy": "azd down"
  }
}
```

To initialize a project with this configuration, run:

```bash
devt init
```

This creates a `workspace.json` file in the current directory if one does not already exist.

## Command Summary

### Adding Tools

- **Repository-based:**
  ```bash
  devt add https://github.com/your-org/your-tool-repo.git
  ```
- **Local Packages:**
  ```bash
  devt local import /path/to/local/package
  ```
  Optionally, specify a group:
  ```bash
  devt local import /path/to/local/package --group custom-group
  ```

### Managing Tools

- **List Tools:**
  ```bash
  devt list
  ```
- **Remove Tools:**
  - Remove a single local tool:
    ```bash
    devt local delete <tool_identifier>
    ```
  - Remove an entire group of local tools:
    ```bash
    devt local delete <group_name> --group
    ```
- **Export Tools:**
  - Export a single tool:
    ```bash
    devt local export <tool_identifier> <destination_path>
    ```
  - Export a group of tools:
    ```bash
    devt local export <group_name> <destination_path> --group
    ```
- **Rename a Group:**
  ```bash
  devt local rename-group <old_group_name> <new_group_name>
  ```
- **Move a Tool:**
  ```bash
  devt local move-tool <tool_identifier> <new_group_name>
  ```

### Script Execution

- **Run a Specific Script:**

  ```bash
  devt do <tool> <script> [arguments]
  ```

  For example:

  ```bash
  devt do testy install
  ```

  This command looks up the tool (preferring workspace-level entries), resolves the correct script for your operating system (e.g. using PowerShell on Windows or Bash on Linux/macOS), and executes it in the appropriate working directory. If auto-sync is enabled for the tool, its repository is updated before executing the script.

- **Standard Commands for Tools:**
  ```bash
  devt install <tool>
  devt uninstall <tool>
  devt upgrade <tool>
  devt version <tool>
  devt test <tool>
  ```

### Project Initialization

- **Initialize Project:**
  ```bash
  devt init
  ```
  This creates a `workspace.json` file in the current directory that can be customized for project-specific tool configurations.

## Cross-Platform and Auto-Sync Features

- **Cross-Platform Support:**  
  Tool packages can define OS-specific scripts under `windows` and `posix` keys in the manifest. DevT resolves and executes the appropriate script based on the current operating system.

- **Auto-Sync:**  
  If a tool package is managed via a Git repository and has auto-sync enabled, DevT will update the repository automatically before executing scripts.

---

## Conclusion

DevT simplifies the way development tools are shared and managed by:

- Centralizing tool definitions in standardized packages.
- Merging workspace and user configurations so that project-specific setups take precedence.
- Providing a flexible, cross-platform execution environment for tool scripts.
- Offering commands for managing (adding, removing, exporting, moving) tools and groups.

With DevT, teams can ensure consistent development environments and focus more on writing code and less on manual configuration.

Happy Coding!

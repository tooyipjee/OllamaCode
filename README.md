# OllamaCode
![OllamaCode Demo](assets/demo.gif)

OllamaCode is a powerful command-line tool for delegating coding tasks to local Large Language Models via Ollama. It provides an agent-like experience similar to Claude Code but running on your local machine, with enhanced features like bash integration and a comprehensive tools framework.

## 🌟 Features

- Interactive chat interface with local LLMs
- Bash command execution directly from the chat
- Extensible tools framework for file operations, web requests, and code execution (experimental)
- Automatic code extraction, saving, and execution
- Configuration system with global and user-specific settings
- Safe mode for restricted bash command execution
- Auto-save and auto-run capabilities for Python code

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
  - [Basic Prompting](#basic-prompting)
  - [Using Tools](#using-tools)
  - [Bash Integration](#bash-integration)
  - [Code Execution](#code-execution)
- [Command Reference](#command-reference)
- [Examples](#examples)
- [Contributing](#contributing)
- [License](#license)

## 🚀 Installation

### Prerequisites

- Python 3.12+
- [Ollama](https://ollama.ai/) installed and running locally

### Install OllamaCode

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ollamacode.git
cd ollamacode
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

## 🏃‍♂️ Quick Start

1. Ensure Ollama is running on your machine
2. Run OllamaCode:
```bash
python ollamacode.py
```

3. Start a conversation:
```
You: Create a Python function to calculate the Fibonacci sequence
```

## ⚙️ Configuration

OllamaCode uses a configuration file system with two levels:

- **Default configuration**: `config.json` in the application directory
- **User configuration**: `~/.config/ollamacode/config.json`

User configuration overrides the default settings. You can customize settings via the command-line interface or by editing the configuration files directly.

### Key Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| `ollama_endpoint` | Ollama API endpoint | http://localhost:11434 |
| `model` | Default Ollama model to use | mistral-nemo:latest |
| `temperature` | Response randomness (0.0-1.0) | 0.7 |
| `enable_bash` | Allow bash command execution | true |
| `enable_tools` | Allow tools execution | true |
| `safe_mode` | Restrict dangerous operations | true |
| `auto_save_code` | Automatically save code to files | false |
| `auto_run_python` | Automatically execute Python code | false |
| `code_directory` | Subdirectory for saved code | "" |
| `process_followup_commands` | Process commands in followup responses | true |
| `max_followup_depth` | Maximum depth for followup responses | 2 |

## 📖 Usage Guide

### Basic Prompting

You can interact with OllamaCode just like any chat-based AI assistant:

```
You: How can I read a CSV file in Python and calculate the average of a column?
```

### Using Tools

OllamaCode provides a rich set of tools that can be invoked by the assistant. You don't need to use special syntax - the assistant will understand contextual requests and use the appropriate tool.

#### Available Tools

1. **file_read**: Read a file's contents
2. **file_write**: Write content to a file
3. **file_list**: List files in a directory
4. **web_get**: Make an HTTP GET request
5. **sys_info**: Get system information
6. **python_run**: Execute a Python script

#### How to Prompt for Tools Usage

Here are examples of how to prompt the assistant to use different tools:

**Reading a file:**
```
You: Can you read the contents of my config.json file?
```

**Writing a file:**
```
You: Save this Python script as fibonacci.py:

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))
```

**Listing files in a directory:**
```
You: What files are in my current working directory?
```

**Making a web request:**
```
You: Can you fetch the latest Bitcoin price from the CoinDesk API?
```

**Getting system information:**
```
You: What operating system am I using and what's my Python version?
```

**Running Python code:**
```
You: Run this code for me:

import random
print([random.randint(1, 100) for _ in range(5)])
```

### Bash Integration

OllamaCode can execute bash commands directly. Simply ask the assistant to perform a shell operation:

```
You: List all processes that are using more than 100MB of memory
```

The assistant will generate and execute the appropriate bash command:

```bash
ps aux --sort=-%mem | awk 'NR==1 || $6 > 102400'
```

For multi-step operations:

```
You: Can you find all Python files in this directory that contain the word "config" and count the lines in each file?
```

### Code Execution

OllamaCode can automatically execute code, especially Python code:

```
You: Can you write and run a Python script that generates 10 random numbers and finds their mean and standard deviation?
```

## 🔍 Command Reference

OllamaCode provides several commands that can be used during the chat:

| Command | Description |
|---------|-------------|
| `/help` | Show help message |
| `/quit` or `/exit` | Exit OllamaCode |
| `/clear` | Clear conversation history |
| `/models` | List available Ollama models |
| `/model <name>` | Switch to a different model |
| `/run` | Extract and run the last code block |
| `/save <path>` | Save the last response to a file |
| `/config` | Show current configuration |
| `/temp <value>` | Set temperature (0.0-1.0) |
| `/tools` | List available tools |
| `/toggle_bash` | Enable/disable bash execution |
| `/toggle_tools` | Enable/disable tools |
| `/toggle_safe` | Enable/disable safe mode |
| `/toggle_auto_save` | Enable/disable automatic code saving |
| `/toggle_auto_run` | Enable/disable automatic Python execution |
| `/list_code` | List saved code files |
| `/workspace` | Show working directory |

## 💡 Examples

### Example 1: File Analysis

```
You: I need to analyze a large CSV file. Can you help me?

OllamaCode: I'd be happy to help you analyze a CSV file. What kind of analysis do you need?

You: First, can you check what CSV files I have in my current directory?

OllamaCode: I'll check for CSV files in your directory.

Executing tool: file_list
Parameters: {"directory": "."}

Tool executed successfully
...
Directory contents of /home/user/ollamacode_workspace:
- 📄 data.csv (2048 bytes)
- 📄 sample.csv (1024 bytes)

You: Great, can you read the first few lines of data.csv to see what kind of data it contains?

OllamaCode: I'll read the first few lines of data.csv to understand its structure.

Executing tool: file_read
Parameters: {"path": "data.csv"}

Tool executed successfully
...
File content (/home/user/ollamacode_workspace/data.csv):
```csv
date,temperature,humidity,pressure
2023-01-01,24.5,65,1013.2
2023-01-02,23.8,68,1012.1
2023-01-03,25.1,62,1011.8
...
```

You: Can you write a Python script to calculate the average temperature for each month?

OllamaCode: I'll create a Python script to calculate the average temperature by month.

```python
import pandas as pd
from datetime import datetime

# Read the CSV file
df = pd.read_csv('data.csv')

# Convert date column to datetime
df['date'] = pd.to_datetime(df['date'])

# Extract month from date
df['month'] = df['date'].dt.strftime('%Y-%m')

# Calculate monthly average temperature
monthly_avg = df.groupby('month')['temperature'].mean().reset_index()

print("Monthly Average Temperatures:")
for _, row in monthly_avg.iterrows():
    print(f"{row['month']}: {row['temperature']:.2f}°C")
```

Executing tool: python_run
Parameters: {"code": "import pandas as pd..."}

Tool executed successfully

Output:
Monthly Average Temperatures:
2023-01: 24.47°C
2023-02: 25.12°C
...
```

### Example 2: Web Data Retrieval and Analysis

```
You: Can you get the current weather for New York and then create a visualization of the 7-day forecast?

OllamaCode: I'll help you get the weather forecast for New York and create a visualization.

Executing tool: web_get
Parameters: {"url": "https://api.openweathermap.org/data/2.5/forecast?q=New%20York&appid=...&units=metric"}

Tool executed successfully
...

Now I'll create a visualization of the 7-day forecast using the API data:

```python
import matplotlib.pyplot as plt
import json
from datetime import datetime

# Parse the weather data
data = json.loads("""
{
  "list": [
    {
      "dt": 1646092800,
      "main": {
        "temp": 8.2,
        ...
      }
    },
    ...
  ]
}
""")

# Extract dates and temperatures
dates = []
temps = []
for item in data['list'][:7]:
    date = datetime.fromtimestamp(item['dt'])
    dates.append(date.strftime('%m-%d'))
    temps.append(item['main']['temp'])

# Create visualization
plt.figure(figsize=(10, 6))
plt.plot(dates, temps, marker='o', linestyle='-', linewidth=2)
plt.title('7-Day Weather Forecast for New York')
plt.xlabel('Date')
plt.ylabel('Temperature (°C)')
plt.grid(True)
plt.savefig('nyc_forecast.png')
plt.show()

print("Visualization saved as nyc_forecast.png")
```
```
Executing tool: python_run
Parameters: {"code": "import matplotlib.pyplot as plt..."}

Tool executed successfully

Output:
Visualization saved as nyc_forecast.png
```
## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the CC0 1.0 Universal License - see the [LICENSE](LICENSE) file for details.

---

Built with ❤️ by Jason Too

For questions and support, please open an issue on GitHub.

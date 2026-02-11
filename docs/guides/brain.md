# Filoma Brain 🧠 (Agentic Analysis)

Connect a "brain" to your filesystem analysis. Filoma integrates with [PydanticAI](https://ai.pydantic.dev/) to allow you to interact with your files using natural language.

The agent doesn't just "talk"—it has **tools** that allow it to scan directories, find duplicates, and inspect metadata in real-time based on your requests.

---

## Quick Start (Step-by-Step)

Follow these 4 steps to get the Filoma Brain running on your machine.

### Step 1: Install Dependencies
Install the optional AI components using the provided Makefile command:
```bash
make brain-install
```

### Step 2: Create your Configuration
Copy the configuration template to a `.env` file:
```bash
cp .env_example .env
```

### Step 3: Configure your Scenario
Open `.env` and choose **ONE** of the following scenarios. Comment out all other scenarios.

#### Scenario A: Mistral AI (Recommended Cloud)
1. Get a key at [console.mistral.ai](https://console.mistral.ai/).
2. Add it to `.env`: `MISTRAL_API_KEY='your-key'`.
3. **Benefit**: European-hosted, high performance, offers a free/experimental tier.

#### Scenario B: Ollama (Recommended Local/Private)
1. Install [Ollama](https://ollama.com/).
2. Pull a model: `ollama pull llama3.1:8b`.
3. Ensure the Ollama app is running.
4. Uncomment the Ollama lines in `.env`:
   ```env
   FILOMA_BRAIN_MODEL='llama3.1:8b'
   FILOMA_BRAIN_BASE_URL='http://localhost:11434/v1'
   ```
5. **Benefit**: 100% private, zero cost, works offline.

### Step 4: Run the Proof of Concept
Verify your setup by running the agentic POC:
```bash
make brain-poc
```
Watch the logs to see the **"Handshake"**—Filoma will tell you exactly which scenario it activated.

### Step 5: Start a Chat Session
You can also chat interactively with your filesystem from the terminal:
```bash
make brain-chat
# OR directly via the CLI:
uv run filoma brain chat
```

---

## Comparison Table

| Feature | Cloud (Mistral) | Local (Ollama) |
| :--- | :--- | :--- |
| **Privacy** | Data sent to provider | 100% Local / Offline |
| **Cost** | Pay-per-token (or free tier) | Zero Cost |
| **Setup** | API Key required | Local App + Model Pull |
| **Hardware** | Works on any machine | Requires decent RAM/GPU |

---

## Usage in your own code

You can easily integrate the brain into your Python scripts.

```python
import asyncio
from filoma.brain import get_agent

async def main():
    # Filoma automatically resolves Scenario A/B from your .env
    agent = get_agent()
    
    # The agent uses filoma tools behind the scenes
    response = await agent.run("Find any duplicate images in ./data/raw and tell me how many groups you found")
    print(f"Brain: {response}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Available Agent Tools

The agent is equipped with the following "eyes and hands":

- **`probe_directory`**: Scans a directory and returns a summary of extensions, file counts, and depth.
- **`find_duplicates`**: Runs Filoma's deduplication engine (Exact, Text, and Image) and reports findings.
- **`get_file_info`**: Retrieves detailed technical metadata for a specific file path.

---

## Troubleshooting

### "Error: AgentRunResult object has no attribute data"
This occurs if you are using an older version of the code. Ensure you have the latest updates from the repository.

### "Connection Refused" (Ollama)
Ensure the Ollama app is running in your system tray or via terminal. Check that `FILOMA_BRAIN_BASE_URL` matches the port Ollama is listening on (usually 11434).

### Key not found
Ensure your `.env` file is in the root of the project where you are running the command. Check for typos in `MISTRAL_API_KEY`.

---

## Future Roadmap: Evals & Reliability

To ensure the Filoma Brain remains accurate and reliable, we are exploring the following advanced [PydanticAI](https://ai.pydantic.dev/) features:

- **Model Evaluation (Evals)**: Implementing automated tests to verify that the agent correctly identifies file distributions and technical metadata without hallucinations.
- **Model Gateway**: Providing a unified interface for switching between multiple models dynamically.
- **Structured Data Extraction**: Moving beyond chat to allow the agent to return complex, validated Pydantic models of your directory structures.

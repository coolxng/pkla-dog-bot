# pkla dog Privacy Policy

**Last updated: August 7, 2026**

This Privacy Policy explains how **pkla dog** (the **Bot**) handles information when you use it on Discord.

The Bot is maintained through the `coolxng/pkla-dog-bot` project. It is an independent application and is not affiliated with or endorsed by Discord Inc.

## 1. Data the Bot may process

The Bot processes only data needed to provide enabled features. Depending on how you interact with it, this may include:

### Discord account and server data

- Discord user IDs;
- usernames and display names supplied by Discord;
- server, channel, and message IDs;
- Discord permission and voice-state information needed for commands and moderation controls;
- the identity of a user invoking a command.

### Message content

When the Bot is configured to respond in a channel, it may process the content of messages in that configured channel in order to respond, maintain short conversation context, run requested commands, or provide AI-assisted features.


### Conversation context and memory

The Bot can keep a bounded amount of conversation context in process memory so that replies can take recent messages into account. It also contains user-invoked memory commands.

Under the verification-ready deployment configuration:

- persistent SQLite conversation storage is disabled;
- automatic memory extraction is disabled;
- conversation context is kept in memory only;
- in-memory context may remain until it is cleared, evicted by the Bot's bounded caches, or the Bot process restarts.

There is no separate time-based expiration timer for ordinary in-memory conversation context.

### Audio and voice data

The Bot can play audio and text-to-speech in Discord voice channels.

The repository also contains browser-based voice receive/listen functionality. **That listen-in functionality is disabled by default in the verification-ready deployment.** When disabled, the Bot does not relay incoming Discord voice audio to the browser-listen feature.

If an operator modifies the deployment to enable voice receive in the future, the operator is responsible for obtaining any required consent, complying with Discord policy and applicable law, and updating this Privacy Policy if the data practices materially change.

Uploaded audio used for playback may be written to a temporary file. The Bot is designed to remove temporary files after validation failures, playback startup failures, or playback completion. A temporary file may remain briefly if the process is forcibly terminated before cleanup finishes.

### Web control data

The Bot includes an authenticated external control page. When enabled, the server may process normal web request metadata and the control credential needed to authorize the session. The authentication cookie is configured as HttpOnly and SameSite=Strict and is marked Secure when served over HTTPS.

Do not share the external control token.

## 2. Why this data is used

Data is processed to:

- respond to user messages and commands;
- maintain short conversation context;
- provide AI-generated replies when requested;
- perform web searches when requested;
- generate text-to-speech when requested;
- connect to and control Discord voice functionality;
- enforce permissions, cooldowns, and abuse protections;
- diagnose errors and keep the service operational.

The Bot does not sell Discord API data and does not use Discord message content to train machine-learning models.

## 3. Third-party services

Some requested features require data to be sent to service providers that process it on behalf of the Bot or provide the requested functionality.

Depending on configuration and the feature used, these services may include:

- **Discord** for the Discord platform and APIs;
- **Groq** for normal AI chat responses;
- **OpenAI** for explicitly enabled AI fallback, web-search, or text-to-speech features;
- search providers such as **DuckDuckGo/DDGS, Tavily, Brave Search, or SerpApi** for requested web-search functionality;
- the Bot's hosting provider for running the application and serving its web interface.

Only data reasonably necessary for the requested feature should be sent to these services. Each provider may process data under its own privacy policy and terms.

## 4. Data storage and retention

The verification-ready deployment is configured to minimize stored Discord API data:

- persistent conversation-history storage is disabled;
- automatic long-term memory extraction is disabled;
- browser voice listen-in is disabled;
- legacy external message forwarding is disabled;
- normal conversation context is stored in memory rather than a persistent database.

In-memory data is lost when the process restarts and may be removed earlier when a user clears active history or when bounded caches evict older entries.

Operational logs may contain technical error information. The Bot is not designed to intentionally log full conversation contents as a general analytics dataset.

If the deployment configuration is materially changed to add persistent storage, the operator must ensure the storage and retention practices comply with Discord's Developer Terms and applicable privacy law before using that configuration for a public deployment.

## 5. Data deletion and correction

Users can clear the Bot's active conversation context in a configured chat by using:

- `!reset`
- `!clear`

Those commands clear the active conversation history used by the Bot for that context.

For deletion, correction, or privacy requests involving any other data associated with your use of pkla dog, contact the project through:

**https://github.com/coolxng/pkla-dog-bot/issues**

When opening a public issue, do **not** include passwords, API keys, authentication tokens, private message contents, financial information, or other sensitive information. Provide only enough information to identify the request and ask for private follow-up if additional information is required.

A valid deletion request will be handled for data controlled by the Bot unless retention is required by applicable law.

Removing the Bot from a server prevents future access to that server through the normal Discord integration, subject to Discord's own platform behavior.

## 6. Security

The project uses measures intended to reduce unauthorized access, including environment-variable secrets, authenticated external controls, bounded uploads, request-size limits, permission checks, and restricted deployment defaults.

No online service can guarantee perfect security. If you believe you found a security or privacy issue, report it through the repository without publishing secrets or exploit details that would put users at risk.

## 7. Children's privacy

The Bot is not directed to children who are not permitted to use Discord under Discord's age requirements or applicable law. Users must meet Discord's eligibility requirements to use the service.

## 8. Changes to this policy

This policy may be updated when the Bot's functionality, service providers, applicable law, or Discord requirements change. The current version will remain publicly available in the project repository and will show its latest update date.

## 9. Contact

Privacy and support requests can be submitted through the project's GitHub repository:

**https://github.com/coolxng/pkla-dog-bot**

Issue tracker:

**https://github.com/coolxng/pkla-dog-bot/issues**

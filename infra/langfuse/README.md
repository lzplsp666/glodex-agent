# Shared Langfuse

This Compose project runs one Langfuse v3 instance for both Glodex and Yuxi.
The web service joins the existing `glodex-agent_default` and
`yuxi-know_app-network` networks with the alias `langfuse`; the storage and
queue services stay on the private `langfuse` network.

## Start

Copy `.env.example` to `.env`, replace every `replace-*` value with generated
secrets, then run:

```powershell
docker compose --env-file .env up -d
docker compose ps
```

Open `http://localhost:3000`, create a project, and use its public/secret keys
in both applications. From a Glodex or Yuxi container the base URL is:

```text
http://langfuse:3000
```

Do not use `localhost` from inside an application container.

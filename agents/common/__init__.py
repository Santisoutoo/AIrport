"""Single source of truth for the code shared by the DEL / GND / TWR pilot agents.

The modules here are vendored into ``agents/<phase>/shared/`` by
``scripts/sync_agent_common.py`` because each agent is built from its own directory
(``gcloud run deploy --source agents/<phase>``), so a container cannot import
anything living above it. Edit the files here, never the vendored copies.
"""

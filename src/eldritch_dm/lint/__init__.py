"""
eldritch_dm.lint — custom lint rules for EldritchDM.

EDM001: Defer-discipline rule. Every Discord interaction callback's
first non-docstring statement must be `await interaction.response.defer(...)`.
"""

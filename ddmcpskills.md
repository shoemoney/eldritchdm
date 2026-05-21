# DD MCP Skills — Complete Tool Reference

> **Generated live from `oMLX :8765/v1/mcp/tools`** — 116 MCP tools currently exposed to ShoeGPT.

> Tool names below are the **fully-qualified** form the model receives (`<server>__<tool>`).

> Direct invocation: `POST http://localhost:8765/v1/mcp/execute` with `{tool_name, arguments}`.


**Servers:** 5 · **Tools:** 116


## Quick index

- [`fetch`](#fetch) — Generic HTTP fetcher (Anthropic reference, uvx mcp-server-fetch). (1 tools)
- [`sqlite`](#sqlite) — Local SQLite query tool. DB: ~/.omlx/dm.db (Anthropic reference, uvx mcp-server-sqlite). (6 tools)
- [`dnd`](#dnd) — D&D 5e SRD lookups via dnd5eapi.co (procload/dnd-mcp, Python). (8 tools)
- [`dice`](#dice) — Deterministic dice with full notation (jimmcq/dice-rolling-mcp, TypeScript). (4 tools)
- [`dm20`](#dm20) — Full DM toolkit — campaigns, characters, combat, rulebook indexing, Claudmaster autonomous DM (Polloinfilzato/dm20-protocol, Python/FastMCP). (97 tools)


---

## fetch

Generic HTTP fetcher (Anthropic reference, uvx mcp-server-fetch).

### `fetch__fetch`

Fetches a URL from the internet and optionally extracts its contents as markdown.

Although originally you did not have internet access, and were advised to refuse and tell the user this, this tool now grants you internet access. Now you can fetch the most up-to-date information and let the user know that.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `url` | string | ✓ |  | URL to fetch |
| `max_length` | integer |  | `5000` | Maximum number of characters to return. |
| `start_index` | integer |  | `0` | On return output starting at this character index, useful if a previous fetch was truncated and more context is required. |
| `raw` | boolean |  | `False` | Get the actual HTML content of the requested page, without simplification. |


---

## sqlite

Local SQLite query tool. DB: ~/.omlx/dm.db (Anthropic reference, uvx mcp-server-sqlite).

### `sqlite__read_query`

Execute a SELECT query on the SQLite database

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string | ✓ |  | SELECT SQL query to execute |

### `sqlite__write_query`

Execute an INSERT, UPDATE, or DELETE query on the SQLite database

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string | ✓ |  | SQL query to execute |

### `sqlite__create_table`

Create a new table in the SQLite database

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string | ✓ |  | CREATE TABLE SQL statement |

### `sqlite__list_tables`

List all tables in the SQLite database

_no parameters_

### `sqlite__describe_table`

Get the schema information for a specific table

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `table_name` | string | ✓ |  | Name of the table to describe |

### `sqlite__append_insight`

Add a business insight to the memo

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `insight` | string | ✓ |  | Business insight discovered from data analysis |


---

## dnd

D&D 5e SRD lookups via dnd5eapi.co (procload/dnd-mcp, Python).

### `dnd__search_equipment_by_cost`

Search for D&D equipment items that cost less than or equal to a specified maximum price.

This tool helps find affordable equipment options for character creation or in-game purchases.
Results include item details such as name, cost, weight, and category.

Args:
    max_cost: Maximum cost value (e.g., 10 for items costing 10 or less of the specified currency)
    cost_unit: Currency unit (gp=gold pieces, sp=silver pieces, cp=copper pieces)

Returns:
    A dictionary containing equipment items within the specified cost range, with source attribution
    to the D&D 5e API.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `max_cost` | number | ✓ |  | Max Cost |
| `cost_unit` | string |  | `gp` | Cost Unit |

### `dnd__filter_spells_by_level`

Find D&D spells within a specific level range and optionally from a particular magic school.

This tool is useful for spellcasters looking for spells they can cast at their current level,
or for finding appropriate spells for NPCs, scrolls, or other magical items. Results include
spell names, levels, schools, and basic casting information.

Args:
    min_level: Minimum spell level (0-9, where 0 represents cantrips)
    max_level: Maximum spell level (0-9, where 9 represents 9th-level spells)
    school: Magic school filter (abjuration, conjuration, divination, enchantment, 
           evocation, illusion, necromancy, transmutation)

Returns:
    A dictionary containing spells that match the specified criteria, with source attribution
    to the D&D 5e API.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `min_level` | integer |  | `0` | Min Level |
| `max_level` | integer |  | `9` | Max Level |
| `school` | string |  | `None` | School |

### `dnd__find_monsters_by_challenge_rating`

Find D&D monsters within a specific challenge rating (CR) range for encounter building.

This tool helps Dungeon Masters find appropriate monsters for encounters based on party level
and desired difficulty. Results include monster names, challenge ratings, types, and basic stats.

Challenge ratings indicate a monster's relative threat level:
- CR 0-4: Low-level threats suitable for parties of levels 1-4
- CR 5-10: Mid-level threats suitable for parties of levels 5-10
- CR 11-16: High-level threats suitable for parties of levels 11-16
- CR 17+: Epic threats suitable for parties of levels 17+

Args:
    min_cr: Minimum challenge rating (0 to 30, can use fractions like 0.25, 0.5)
    max_cr: Maximum challenge rating (0 to 30)

Returns:
    A dictionary containing monsters within the specified CR range, with source attribution
    to the D&D 5e API.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `min_cr` | number |  | `0` | Min Cr |
| `max_cr` | number |  | `30` | Max Cr |

### `dnd__get_class_starting_equipment`

Get starting equipment for a character class.

Args:
    class_name: Name of the character class

Returns:
    Starting equipment for the class

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `class_name` | string | ✓ |  | Class Name |

### `dnd__search_all_categories`

Search across all D&D 5e API categories for any D&D content matching the query.

This is the primary search tool for finding D&D content. It searches across all available
categories including spells, monsters, equipment, classes, races, magic items, and more.
Results are ranked by relevance and include a "top results" section showing the best matches
across all categories.

The search is intelligent and considers:
- Exact name matches
- Partial name matches
- Matches in descriptions
- Content relevance to the query
- D&D-specific synonyms and abbreviations
- Special D&D terms and notation
- Common misspellings of D&D terms

For more specific searches, consider using category-specific tools like filter_spells_by_level
or find_monsters_by_challenge_rating.

Args:
    query: Search term (minimum 3 characters) to find across all D&D content

Returns:
    A comprehensive dictionary containing matching items across all categories, organized by
    category with a "top_results" section highlighting the best matches, and source attribution
    to the D&D 5e API.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string | ✓ |  | Query |

### `dnd__verify_with_api`

Verify the accuracy of a D&D statement by checking it against the official D&D 5e API data.

This tool analyzes a statement about D&D 5e rules, creatures, spells, or other game elements
and verifies its accuracy by searching the official D&D 5e API. It extracts key terms from
the statement and searches for relevant information.

The verification process:
1. Extracts key terms from the statement
2. Searches the D&D 5e API for these terms
3. Analyzes the search results to verify the statement
4. Returns the verification results with confidence levels
5. Includes source attribution for all information

Args:
    statement: The D&D statement to verify (e.g., "Fireball is a 3rd-level evocation spell")
    category: Optional category to focus the search (e.g., "spells", "monsters", "classes")

Returns:
    A dictionary containing verification results, relevant D&D information, and source attribution.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `statement` | string | ✓ |  | Statement |
| `category` | string |  | `None` | Category |

### `dnd__check_api_health`

Check the health and status of the D&D 5e API.

This tool verifies that the D&D 5e API is operational and provides information
about available endpoints and resources. It's useful for diagnosing issues or
understanding what data is available.

The health check includes:
1. Verifying the base API endpoint is accessible
2. Checking key endpoints (spells, monsters, classes)
3. Reporting on available categories and their status
4. Providing counts of available resources

Returns:
    A dictionary containing API status information, available endpoints,
    resource counts, and source attribution to the D&D 5e API.

_no parameters_

### `dnd__generate_treasure_hoard`

Generate D&D 5e treasure based on challenge rating and context.

This tool creates appropriate treasure for encounters or dungeons following the
Dungeon Master's Guide treasure tables. It uses official D&D 5e API data for
equipment and magic items to ensure accuracy.

The treasure is balanced according to the challenge rating provided, with higher
CR values resulting in more valuable treasure. Final treasure (such as at the end
of a dungeon) can be made more significant by setting is_final_treasure to True.

Args:
    challenge_rating: The challenge rating to base treasure on (0.25 to 30)
    is_final_treasure: Whether this is a climactic treasure (increases value)
    treasure_type: Type of treasure to generate ("individual" or "hoard")

Returns:
    A dictionary containing generated treasure including coins, equipment items, and magic items
    with source attribution to the D&D 5e API.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `challenge_rating` | number | ✓ |  | Challenge Rating |
| `is_final_treasure` | boolean |  | `False` | Is Final Treasure |
| `treasure_type` | string |  | `hoard` | Treasure Type |


---

## dice

Deterministic dice with full notation (jimmcq/dice-rolling-mcp, TypeScript).

### `dice__search`

Search dice rolling documentation, guides, and examples

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string | ✓ |  | Search query to find relevant dice rolling information, examples, or notation help |

### `dice__fetch`

Retrieve detailed content for a specific dice rolling topic by ID

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `id` | string | ✓ |  | ID of the dice rolling topic to fetch (from search results) |

### `dice__dice_roll`

Roll dice using standard notation. IMPORTANT: For D&D advantage use "2d20kh1" (NOT "2d20")

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `notation` | string | ✓ |  | Dice notation. Examples: "1d20+5" (basic), "2d20kh1" (advantage), "2d20kl1" (disadvantage), "4d6kh3" (stats), "3d6!" (exploding) |
| `label` | string |  |  | Optional label e.g., "Attack roll", "Fireball damage" |
| `verbose` | boolean |  |  | Show detailed breakdown of individual dice results |

### `dice__dice_validate`

Validate and explain dice notation without rolling. Use this to understand what notation means before rolling

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `notation` | string | ✓ |  | Dice notation to validate and explain. Examples: "2d20kh1+5", "4d6kh3", "8d6", "1d%" |


---

## dm20

Full DM toolkit — campaigns, characters, combat, rulebook indexing, Claudmaster autonomous DM (Polloinfilzato/dm20-protocol, Python/FastMCP).

### `dm20__create_campaign`

Create a new D&D campaign.

The rules_version parameter selects which edition of the D&D 5e rules
to use for this campaign. '2024' uses the revised 2024 rules, '2014'
uses the original 5th edition rules.

The interaction_mode parameter controls how the DM communicates:
- classic: Text-only, no voice dependencies required.
- narrated: DM responses delivered as TTS audio + text via WebSocket.
- immersive: Narrated + player STT input from browser.

Interaction mode and model profile are independent axes — any combination is valid.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Campaign name |
| `description` | string | ✓ |  | Brief decription of the campaign, or a tagline |
| `dm_name` | string | null |  | `None` | Dungeon Master name |
| `setting` | string | string | null |  | `None` | Campaign setting - a full description of the setting of the campaign in markdown format, or the path to a `.txt` or `.md` file containing the same. |
| `rules_version` | string |  | `2024` | D&D rules version: '2014' or '2024' (default: '2024') |
| `interaction_mode` | enum: ['classic', 'narrated', 'immersive'] |  | `classic` | Interaction mode: 'classic' (text-only), 'narrated' (TTS audio + text), 'immersive' (narrated + STT input). Default: 'classic' |

### `dm20__get_campaign_info`

Get information about the current campaign.

Returns campaign information including name, description, counts of various entities,
and current game state.

_no parameters_

### `dm20__list_campaigns`

List all available campaigns.

_no parameters_

### `dm20__load_campaign`

Load a specific campaign.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Campaign name to load |

### `dm20__delete_campaign`

Delete a campaign permanently. This cannot be undone.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Campaign name to delete |

### `dm20__create_character`

Create a new player character.

When a rulebook is loaded, auto-populates the character with saving throws,
proficiencies, starting equipment, features, HP, spell slots, and more from
the class, race, and background definitions. Requires a rulebook to be loaded
(use load_rulebook source="srd" first).

Without a rulebook, returns an error message asking to load one first.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Character name |
| `character_class` | string | ✓ |  | Primary character class |
| `class_level` | integer | ✓ |  | Primary class level |
| `race` | string | ✓ |  | Character race |
| `player_name` | string | null |  | `None` | The name of the player in control of this character |
| `description` | string | null |  | `None` | A brief description of the character's appearance and demeanor. |
| `bio` | string | null |  | `None` | The character's backstory, personality, and motivations. |
| `background` | string | null |  | `None` | Character background |
| `alignment` | string | null |  | `None` | Character alignment |
| `subclass` | string | null |  | `None` | Primary class subclass name (required if level >= subclass level) |
| `subrace` | string | null |  | `None` | Subrace name (e.g., 'Hill Dwarf') |
| `additional_classes` | string | null |  | `None` | JSON list for multiclass: [{"name": "Wizard", "level": 3, "subclass": "Evocation"}] |
| `ability_method` | string |  | `manual` | Ability score method: 'manual' (default), 'standard_array', or 'point_buy' |
| `ability_assignments` | string | null |  | `None` | JSON dict for standard_array/point_buy: {"strength": 15, "dexterity": 14, ...} |
| `strength` | integer |  | `10` | Strength score (manual mode) |
| `dexterity` | integer |  | `10` | Dexterity score (manual mode) |
| `constitution` | integer |  | `10` | Constitution score (manual mode) |
| `intelligence` | integer |  | `10` | Intelligence score (manual mode) |
| `wisdom` | integer |  | `10` | Wisdom score (manual mode) |
| `charisma` | integer |  | `10` | Charisma score (manual mode) |

### `dm20__level_up_character`

Level up a character by one level.

Increments level, calculates HP increase, adds class features, updates
spell slots for casters, handles ASI at appropriate levels, and manages
subclass selection. Requires a rulebook to be loaded.

Multiclass: if class_name is a class the character doesn't have yet,
this acts as a multiclass dip — adding that class at level 1.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `class_name` | string | null |  | `None` | Which class to level up (for multiclass characters). If omitted, levels up primary class. |
| `hp_method` | string |  | `average` | HP increase method: 'average' (default, PHB standard) or 'roll' |
| `asi_choices` | string | null |  | `None` | JSON dict for ASI: {"strength": 2} or {"strength": 1, "dexterity": 1} |
| `subclass` | string | null |  | `None` | Subclass to select (at subclass level, typically 3) |
| `new_spells` | string | null |  | `None` | JSON list of new spells learned: ["fireball", "counterspell"] |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__get_character`

Get detailed character information. Accepts character name, ID, or player name.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name_or_id` | string | ✓ |  | Character name, ID, or player name |

### `dm20__update_character`

Update a character's properties.

Supports scalar field updates, ability score changes, and list add/remove
operations for conditions, proficiencies, languages, and features.
List parameters accept JSON arrays (e.g. '["poisoned","prone"]') or
comma-separated strings (e.g. 'poisoned,prone').

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name_or_id` | string | ✓ |  | Character name, ID, or player name. |
| `name` | string | null |  | `None` | New character name. If you change this, you must use the character's ID to identify them. |
| `player_name` | string | null |  | `None` | The name of the player in control of this character |
| `description` | string | null |  | `None` | A brief description of the character's appearance and demeanor. |
| `bio` | string | null |  | `None` | The character's backstory, personality, and motivations. |
| `background` | string | null |  | `None` | Character background |
| `alignment` | string | null |  | `None` | Character alignment |
| `hit_points_current` | integer | null |  | `None` | Current hit points |
| `hit_points_max` | integer | null |  | `None` | Maximum hit points |
| `temporary_hit_points` | integer | null |  | `None` | Temporary hit points |
| `armor_class` | integer | null |  | `None` | Armor class |
| `experience_points` | integer | null |  | `None` | Experience points |
| `speed` | integer | null |  | `None` | Movement speed in feet |
| `character_level` | integer | null |  | `None` | Set the primary class level directly (e.g. to downgrade to level 1). Recalculates proficiency bonus automatically. |
| `hit_dice_remaining` | string | null |  | `None` | Remaining hit dice, e.g. '1d8' or '3d10'. Use after a level change or manual rest. |
| `inspiration` | boolean | null |  | `None` | Inspiration status |
| `notes` | string | null |  | `None` | Additional notes about the character |
| `strength` | integer | null |  | `None` | Strength score |
| `dexterity` | integer | null |  | `None` | Dexterity score |
| `constitution` | integer | null |  | `None` | Constitution score |
| `intelligence` | integer | null |  | `None` | Intelligence score |
| `wisdom` | integer | null |  | `None` | Wisdom score |
| `charisma` | integer | null |  | `None` | Charisma score |
| `add_conditions` | string | null |  | `None` | JSON list of conditions to add, e.g. '["poisoned","prone"]' |
| `remove_conditions` | string | null |  | `None` | JSON list of conditions to remove |
| `add_skill_proficiencies` | string | null |  | `None` | JSON list of skill proficiencies to add |
| `remove_skill_proficiencies` | string | null |  | `None` | JSON list of skill proficiencies to remove |
| `add_tool_proficiencies` | string | null |  | `None` | JSON list of tool proficiencies to add |
| `remove_tool_proficiencies` | string | null |  | `None` | JSON list of tool proficiencies to remove |
| `add_languages` | string | null |  | `None` | JSON list of languages to add |
| `remove_languages` | string | null |  | `None` | JSON list of languages to remove |
| `add_saving_throw_proficiencies` | string | null |  | `None` | JSON list of saving throw proficiencies to add |
| `remove_saving_throw_proficiencies` | string | null |  | `None` | JSON list of saving throw proficiencies to remove |
| `add_features_and_traits` | string | null |  | `None` | JSON list of features/traits to add |
| `remove_features_and_traits` | string | null |  | `None` | JSON list of features/traits to remove |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__bulk_update_characters`

Update properties for multiple characters at once by a given amount.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `names_or_ids` | array | ✓ |  | List of character names, IDs, or player names to update. |
| `hp_change` | integer | null |  | `None` | Amount to change current HP by (positive or negative). |
| `temp_hp_change` | integer | null |  | `None` | Amount to change temporary HP by (positive or negative). |
| `strength_change` | integer | null |  | `None` | Amount to change strength by. |
| `dexterity_change` | integer | null |  | `None` | Amount to change dexterity by. |
| `constitution_change` | integer | null |  | `None` | Amount to change constitution by. |
| `intelligence_change` | integer | null |  | `None` | Amount to change intelligence by. |
| `wisdom_change` | integer | null |  | `None` | Amount to change wisdom by. |
| `charisma_change` | integer | null |  | `None` | Amount to change charisma by. |

### `dm20__add_item_to_character`

Add an item to a character's inventory.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name. |
| `item_name` | string | ✓ |  | Item name |
| `description` | string | null |  | `None` | Item description |
| `quantity` | integer |  | `1` | Quantity |
| `item_type` | string |  | `misc` | Item type (e.g., 'weapon', 'armor', 'consumable', 'misc', 'treasure', 'tool', 'quest') |
| `weight` | number | null |  | `None` | Item weight |
| `value` | string | null |  | `None` | Item value (e.g., '50 gp') |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__equip_item`

Equip an item from inventory to an equipment slot.

Moves the item from the character's inventory to the specified equipment slot.
If the slot is already occupied, the current item is automatically unequipped
back to inventory first.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `item_name_or_id` | string | ✓ |  | Item name or ID from inventory |
| `slot` | string | ✓ |  | Equipment slot: weapon_main, weapon_off, armor, or shield |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__unequip_item`

Unequip an item from an equipment slot back to inventory.

Moves the equipped item back to the character's inventory and clears the slot.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `slot` | string | ✓ |  | Equipment slot: weapon_main, weapon_off, armor, or shield |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__remove_item`

Remove an item from a character's inventory.

Removes the specified quantity of an item. If quantity is greater than or equal
to the item's current quantity, the item is removed entirely.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `item_name_or_id` | string | ✓ |  | Item name or ID to remove |
| `quantity` | integer |  | `1` | Quantity to remove (default: all) |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__use_spell_slot`

Use a spell slot, decrementing available slots for the given level.

Validates that the character has slots at this level and that at least
one is still available. Returns remaining slot count.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `slot_level` | integer | ✓ |  | Spell slot level to use (1-9) |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__add_spell`

Add a spell to a character's spells known list.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `spell_name` | string | ✓ |  | Spell name |
| `spell_level` | integer | ✓ |  | Spell level (0 for cantrip) |
| `school` | string |  | `unknown` | School of magic (e.g. 'evocation', 'abjuration') |
| `casting_time` | string |  | `1 action` | Casting time (e.g. '1 action') |
| `spell_range` | integer |  | `5` | Range in feet |
| `duration` | string |  | `instantaneous` | Duration (e.g. 'instantaneous') |
| `components` | string | null |  | `None` | JSON list of components, e.g. '["V","S","M"]' |
| `spell_description` | string |  | `''` | Spell description |
| `prepared` | boolean |  | `False` | Whether the spell is prepared |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__remove_spell`

Remove a spell from a character's spells known list.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `spell_name_or_id` | string | ✓ |  | Spell name or ID to remove |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__long_rest`

Perform a long rest for a character.

Resets spell slots, restores hit dice (half of total, minimum 1),
clears death saves, and optionally restores HP to maximum.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `restore_hp` | boolean |  | `True` | Restore HP to maximum (default: true) |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__short_rest`

Perform a short rest for a character.

Optionally spend hit dice to regain hit points. Each hit die rolled
adds 1dX + CON modifier HP (minimum 1 per die).

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `hit_dice_to_spend` | integer |  | `0` | Number of hit dice to spend for healing |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__add_death_save`

Record a death saving throw result.

Tracks successes and failures. At 3 successes, the character stabilizes
(HP set to 1, death saves reset). At 3 failures, the character dies.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `success` | boolean | ✓ |  | True for success, False for failure |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__list_characters`

List all characters in the current campaign.

Returns a list of all player characters with their basic information.

_no parameters_

### `dm20__delete_character`

Delete a character from the current campaign. Accepts character name, ID, or player name.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name_or_id` | string | ✓ |  | Character name, ID, or player name. |

### `dm20__create_npc`

Create a new NPC.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | NPC name |
| `description` | string | null |  | `None` | A brief, public description of the NPC. |
| `bio` | string | null |  | `None` | A detailed, private bio for the NPC, including secrets. |
| `race` | string | null |  | `None` | NPC race |
| `occupation` | string | null |  | `None` | NPC occupation |
| `location` | string | null |  | `None` | Current location |
| `attitude` | string | null |  | `None` | Attitude towards party |
| `notes` | string |  | `''` | Additional notes |

### `dm20__get_npc`

Get NPC information.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name_or_id` | string | ✓ |  | NPC name or ID |
| `player_id` | string | null |  | `None` | Caller's player ID for output filtering. When provided, DM-only fields (bio, notes, stats, relationships) are stripped for non-DM callers. |

### `dm20__list_npcs`

List all NPCs in the current campaign.

Returns a list of all non-player characters with their basic information.

_no parameters_

### `dm20__create_location`

Create a new location.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Location name |
| `location_type` | string | ✓ |  | Type of location (city, town, village, dungeon, etc.) |
| `description` | string | ✓ |  | Location description |
| `population` | integer | null |  | `None` | Population (if applicable) |
| `government` | string | null |  | `None` | Government type |
| `notable_features` | array | null |  | `None` | Notable features |
| `notes` | string |  | `''` | Additional notes |

### `dm20__get_location`

Get location information.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Location name |
| `discovery_filter` | boolean |  | `False` | Filter notable features by discovery state. When True, only features the party has discovered (GLIMPSED+) are shown. Default: False |
| `player_id` | string | null |  | `None` | Caller's player ID for output filtering. When provided, combines discovery filter + permission filter: non-DM callers see only discovered features and no DM notes. |

### `dm20__list_locations`

List all locations in the current campaign.

Returns a list of all locations with their basic information.

_no parameters_

### `dm20__create_quest`

Create a new quest.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `title` | string | ✓ |  | Quest title |
| `description` | string | ✓ |  | Quest description |
| `giver` | string | null |  | `None` | Quest giver (NPC name) |
| `objectives` | array | null |  | `None` | Quest objectives |
| `reward` | string | null |  | `None` | Quest reward |
| `notes` | string |  | `''` | Additional notes |

### `dm20__update_quest`

Update quest status or complete objectives.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `title` | string | ✓ |  | Quest title |
| `status` | string | null |  | `None` | New quest status |
| `completed_objective` | string | null |  | `None` | Objective to mark as completed |

### `dm20__list_quests`

List quests, optionally filtered by status.

Returns a list of quests with their basic information and status.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `status` | string | null |  | `None` | Filter by status |

### `dm20__update_game_state`

Update the current game state.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `current_location` | string | null |  | `None` | Current party location |
| `current_session` | integer | null |  | `None` | Current session number |
| `current_date_in_game` | string | null |  | `None` | Current in-game date |
| `party_level` | integer | null |  | `None` | Average party level |
| `party_funds` | string | null |  | `None` | Party treasure/funds |
| `in_combat` | boolean | null |  | `None` | Whether party is in combat |
| `notes` | string | null |  | `None` | Current situation notes |

### `dm20__get_game_state`

Get the current game state.

_no parameters_

### `dm20__start_combat`

Start a combat encounter.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `participants` | array | ✓ |  | Combat participants with initiative order |

### `dm20__end_combat`

End the current combat encounter.

_no parameters_

### `dm20__next_turn`

Advance to the next turn in combat.

_no parameters_

### `dm20__combat_action`

Resolve a combat action via the pipeline, apply results, and return a formatted outcome.

Supports weapon attacks (melee/ranged) and saving throw spells. Automatically
applies damage to the target's HP, triggers concentration checks, and reports
the full mechanical outcome. This is additive -- it does not replace manual
roll_dice workflows.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `attacker` | string | ✓ |  | Name of the attacking character or NPC |
| `target` | string | ✓ |  | Name of the target character or NPC |
| `action_type` | string |  | `attack` | Action type: 'attack' for weapon/melee/ranged, 'save_spell' for saving throw spells |
| `weapon_or_spell` | string | null |  | `None` | Weapon name (from inventory) or spell name. None uses equipped main weapon. |
| `damage_dice` | string | null |  | `None` | Override damage dice (e.g., '8d6' for fireball). Only for save_spell actions. |
| `damage_type` | string | null |  | `None` | Damage type (e.g., 'fire', 'slashing'). Only for save_spell actions. |
| `save_ability` | string | null |  | `None` | Saving throw ability (e.g., 'dexterity'). Required for save_spell actions. |
| `half_on_save` | boolean |  | `False` | Whether successful save deals half damage. Only for save_spell actions. |
| `spell_dc` | integer | null |  | `None` | Override spell save DC. Only for save_spell actions. |

### `dm20__build_encounter_tool`

Return encounter suggestions with monster compositions based on party size, level, and difficulty.

Uses the D&D 5e encounter building rules (DMG Chapter 3) to calculate XP budgets
and suggest balanced encounters. When rulebooks are loaded, suggests specific monsters.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `party_size` | integer | ✓ |  | Number of party members |
| `party_level` | integer | ✓ |  | Average party level |
| `difficulty` | string |  | `medium` | Encounter difficulty: 'easy', 'medium', 'hard', 'deadly' |
| `creature_type` | string | null |  | `None` | Optional creature type filter (e.g., 'undead', 'beast') |
| `environment` | string | null |  | `None` | Optional environment filter (e.g., 'forest', 'cave') |

### `dm20__show_map`

Render the current tactical map as ASCII art.

Shows positions of all combat participants on a grid. Returns
'No tactical map active' if no positions are set or no combat is active.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `highlight_aoe` | string | null |  | `None` | Optional AoE description to highlight (e.g., 'sphere 20ft at 5,5') |

### `dm20__apply_effect`

Apply an ActiveEffect to a character (SRD condition or custom effect).

For SRD conditions (blinded, charmed, deafened, exhaustion, frightened,
grappled, incapacitated, invisible, paralyzed, petrified, poisoned,
prone, restrained, stunned), uses the standard condition template.

For custom effects, creates a new ActiveEffect with the provided modifiers.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name. |
| `effect_name` | string | ✓ |  | Effect name (SRD condition like 'blinded', 'poisoned', or custom name) |
| `source` | string | null |  | `None` | Source of the effect (e.g., 'Poison trap', 'Hold Person spell') |
| `duration` | integer | null |  | `None` | Duration in rounds. None for permanent effects. |
| `custom_modifiers` | string | null |  | `None` | JSON list of custom modifiers, e.g. '[{"stat":"attack_roll","operation":"add","value":2}]' |

### `dm20__remove_effect`

Remove an active effect from a character by ID or name.

If an exact effect ID is provided, removes that specific instance.
If a name is provided, removes all effects with that name.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name_or_id` | string | ✓ |  | Character name, ID, or player name. |
| `effect_id_or_name` | string | ✓ |  | Effect ID (exact match) or effect name (removes all with that name) |

### `dm20__add_session_note`

Add notes for a game session.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `session_number` | integer | ✓ |  | Session number |
| `summary` | string | ✓ |  | Session summary |
| `title` | string | null |  | `None` | Session title |
| `events` | string | null |  | `None` | Key events that occurred (JSON list or comma-separated) |
| `characters_present` | string | null |  | `None` | Characters present in session (JSON list or comma-separated) |
| `npcs_encountered` | string | null |  | `None` | NPCs encountered in session (JSON list or comma-separated) |
| `quest_updates` | string | null |  | `None` | Quest name to progress mapping (JSON object) |
| `combat_encounters` | string | null |  | `None` | Combat encounter summaries (JSON list or comma-separated) |
| `experience_gained` | integer | null |  | `None` | Experience points gained |
| `treasure_found` | string | null |  | `None` | Treasure or items found (JSON list or comma-separated) |
| `notes` | string |  | `''` | Additional notes |

### `dm20__summarize_session`

Generate structured SessionNote from a raw session transcription.

This tool accepts either raw transcription text or a path to a transcription file,
then generates a comprehensive structured summary including events, NPCs encountered,
quest updates, and combat encounters. The tool leverages campaign context (characters,
NPCs, locations, quests) to enrich the summary.

For large transcriptions (>200k characters ≈ 50k tokens), the tool automatically
chunks the input into overlapping segments for processing.

Args:
    transcription: Raw text or file path containing session transcription
    session_number: Session number for this recording
    detail_level: Amount of detail in the generated summary
    speaker_map: Optional mapping of generic speaker labels to character names

Returns:
    Prompt for LLM to generate SessionNote

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `transcription` | string | ✓ |  | Raw transcription text or path to transcription file |
| `session_number` | integer | ✓ |  | Session number |
| `detail_level` | enum: ['brief', 'medium', 'detailed'] |  | `medium` | Detail level for the summary |
| `speaker_map` | object | null |  | `None` | Speaker label to character mapping (e.g., {'Speaker 1': 'Gandalf'}) |

### `dm20__get_sessions`

Get all session notes.

_no parameters_

### `dm20__add_event`

Add an event to the adventure log.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `event_type` | enum: ['combat', 'roleplay', 'exploration', 'quest', 'character', 'world', 'session', 'social'] | ✓ |  | Type of event |
| `description` | string | ✓ |  | Event description |
| `title` | string | null |  | `None` | Event title (optional, auto-generated from description if omitted) |
| `session_number` | integer | null |  | `None` | Session number |
| `characters_involved` | string | null |  | `None` | Characters involved — list or JSON array string, e.g. '["name1","name2"]' |
| `location` | string | null |  | `None` | Location where event occurred |
| `importance` | integer |  | `3` | Event importance (1-5) |
| `tags` | string | null |  | `None` | Tags for categorizing the event — list or JSON array string, e.g. '["npc","story"]' |

### `dm20__get_events`

Get events from the adventure log.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `limit` | integer | null |  | `None` | Maximum number of events to return |
| `event_type` | string | null |  | `None` | Filter by event type |
| `search` | string | null |  | `None` | Search events by title/description |

### `dm20__load_rulebook`

Load a rulebook into the current campaign.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `source` | enum: ['srd', 'custom', 'open5e', '5etools'] | ✓ |  | Source type: 'srd' for official D&D 5e SRD, 'custom' for local files, 'open5e' for Open5e API, '5etools' for 5etools JSON data |
| `version` | string | null |  | `2014` | SRD version: '2014' (default) or '2024'. Ignored for custom sources. |
| `path` | string | null |  | `None` | Path to custom rulebook file (JSON). Required for custom sources. |

### `dm20__list_rulebooks`

List all active rulebooks in the current campaign.

_no parameters_

### `dm20__unload_rulebook`

Remove a rulebook from the current campaign.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `source_id` | string | ✓ |  | ID of the rulebook to unload (from list_rulebooks) |

### `dm20__search_rules`

Search for rules content across all loaded rulebooks.

Works without a campaign loaded (uses global rulebook manager).
When a campaign is active, its rulebook manager takes priority.

Examples:
    - search_rules(query="fire", category="spell") - Find spells with 'fire' in name
    - search_rules(class_filter="ranger", category="spell") - All ranger spells
    - search_rules(query="cure", class_filter="ranger", category="spell") - Ranger spells with 'cure' in name

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string |  | `''` | Search term (name, partial match). Can be empty if class_filter is provided. |
| `category` | string | null |  | `all` | Filter by category. Default: all |
| `limit` | integer |  | `20` | Max results |
| `class_filter` | string | null |  | `None` | Filter spells by class (e.g., 'ranger', 'wizard'). Only applies to spell category. |

### `dm20__get_class_info`

Get full class definition from loaded rulebooks.

Works without a campaign loaded (uses global rulebook manager).
When a campaign is active, its rulebook manager takes priority.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Class name (e.g., 'wizard', 'fighter') |
| `level` | integer | null |  | `None` | Show features up to this level |

### `dm20__get_race_info`

Get full race definition from loaded rulebooks.

Works without a campaign loaded (uses global rulebook manager).
When a campaign is active, its rulebook manager takes priority.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Race name (e.g., 'elf', 'dwarf') |

### `dm20__get_spell_info`

Get spell details from loaded rulebooks.

Works without a campaign loaded (uses global rulebook manager).
When a campaign is active, its rulebook manager takes priority.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Spell name (e.g., 'fireball', 'cure wounds') |

### `dm20__get_monster_info`

Get monster stat block from loaded rulebooks.

Works without a campaign loaded (uses global rulebook manager).
When a campaign is active, its rulebook manager takes priority.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Monster name (e.g., 'goblin', 'adult red dragon') |

### `dm20__validate_character_rules`

Validate a character against loaded rulebooks.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name_or_id` | string | ✓ |  | Character name or ID to validate |

### `dm20__roll_dice`

Roll dice with D&D notation.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `dice_notation` | string | ✓ |  | Dice notation (e.g., '1d20', '3d6+2') |
| `advantage` | boolean |  | `False` | Roll with advantage |
| `disadvantage` | boolean |  | `False` | Roll with disadvantage |
| `label` | string |  | `''` | Context label for the roll (e.g., 'Goblin Archer 2 attack vs Aldric') |

### `dm20__calculate_experience`

Calculate experience points for an encounter.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `party_size` | integer | ✓ |  | Number of party members |
| `party_level` | integer | ✓ |  | Average party level |
| `encounter_xp` | integer | ✓ |  | Total encounter XP value |

### `dm20__open_library_folder`

Open the library folder where users can drop PDF and Markdown rulebooks.

Creates the library/pdfs/ directory if it doesn't exist, then opens it
in the system file manager (Finder on macOS, file manager on Linux).

Returns the absolute path to the folder with instructions on next steps.

_no parameters_

### `dm20__scan_library`

Scan the library folder for new PDF/Markdown files and index them.

Scans the library/pdfs/ directory for PDF and Markdown files,
extracts table of contents from new or modified files,
and saves indexes for quick searching.

Returns a summary of files found and indexed.

_no parameters_

### `dm20__list_library`

List all sources in the library with their content summaries.

Returns a formatted list of all PDF and Markdown sources
in the library, showing their index status and content counts.

_no parameters_

### `dm20__get_library_toc`

Get the table of contents for a specific library source.

Returns the full hierarchical table of contents extracted from
the PDF or Markdown source, with page numbers and content types.

Args:
    source_id: The source identifier (use list_library to see available sources)

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `source_id` | string | ✓ |  | The source identifier (e.g., 'tome-of-heroes') |

### `dm20__search_library`

Search across all indexed library content.

Searches TOC entries by title across all indexed PDF and Markdown sources.
Can filter by content type (class, race, spell, etc.).

Args:
    query: Search term (case-insensitive, searches in titles)
    content_type: Filter by content type (default: all)
    limit: Maximum results to return (default: 20)

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string |  | `''` | Search term (searches titles) |
| `content_type` | enum: ['all', 'class', 'race', 'spell', 'monster', 'feat', 'item', 'background', 'subclass'] |  | `all` | Filter by content type |
| `limit` | integer |  | `20` | Maximum results to return |

### `dm20__ask_books`

Ask a natural language question across all your rulebooks.

Uses keyword expansion with D&D concept synonyms and TF-IDF scoring
to find relevant content across all indexed PDF and Markdown sources.

Examples:
    - "What options do I have for a melee spellcaster?"
    - "Find a class good for a dragon-themed character"
    - "What healing spells are available?"
    - "Show me tanky fighter options"
    - "Classes with nature magic"

Args:
    query: Natural language question or search query
    limit: Maximum number of results to return (default: 10)

Returns:
    Formatted search results grouped by source

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string | ✓ |  | Natural language question about your rulebooks |
| `limit` | integer |  | `10` | Maximum number of results to return |

### `dm20__extract_content`

Extract content from a PDF source and save as CustomSource JSON.

Extracts the full content definition from a PDF source based on the
table of contents entry. The extracted content is saved to the
library/extracted/{source_id}/ directory in CustomSource JSON format,
ready to be loaded by the rulebook system.

Examples:
    - extract_content("tome-of-heroes", "Fighter", "class")
    - extract_content("phb", "Elf", "race")
    - extract_content("phb", "Fireball", "spell")

Args:
    source_id: The source identifier (use list_library to see available sources)
    content_name: Name of the content to extract (as shown in TOC)
    content_type: Type of content (class, race, spell, monster, feat, item)

Returns:
    Success message with path to extracted file, or error message

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `source_id` | string | ✓ |  | The source identifier (e.g., 'tome-of-heroes') |
| `content_name` | string | ✓ |  | Name of the content to extract (e.g., 'Fighter', 'Elf') |
| `content_type` | enum: ['class', 'race', 'spell', 'monster', 'feat', 'item'] | ✓ |  | Type of content to extract |

### `dm20__enable_library_source`

Enable a library source for the current campaign.

Adds a library source to the campaign's enabled content. You can enable
the entire source or filter by content type and specific items.

Examples:
    - enable_library_source("tome-of-heroes") - Enable all content
    - enable_library_source("tome-of-heroes", content_type="class") - Enable all classes
    - enable_library_source("tome-of-heroes", content_type="class", content_names=["dragon-knight"]) - Enable specific class

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `source_id` | string | ✓ |  | The source identifier (e.g., 'tome-of-heroes') |
| `content_type` | string | null |  | `all` | Filter by content type. Use 'all' or omit to enable entire source. |
| `content_names` | array | null |  | `None` | Specific content names to enable (e.g., ['dragon-knight', 'shadow-dancer']). Only used if content_type is specified. |

### `dm20__disable_library_source`

Disable a library source for the current campaign.

Removes a library source from the campaign's enabled content.
The source will no longer be available for use in this campaign.

Args:
    source_id: The source identifier (use list_enabled_library to see enabled sources)

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `source_id` | string | ✓ |  | The source identifier to disable |

### `dm20__list_enabled_library`

List all library sources enabled for the current campaign.

Returns a formatted list of all library sources that have been
enabled for use in the current campaign, including any content filters.

_no parameters_

### `dm20__configure_claudmaster`

Configure the Claudmaster AI DM settings for the current campaign.

Call with no arguments to view current configuration.
Provide specific fields to update only those settings (partial update).
Set model_profile to switch all model settings at once (quality/balanced/economy).
Set interaction_mode to switch how the DM communicates (independent of model_profile).
Set reset_to_defaults=True to restore all settings to their default values.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `llm_model` | string | null |  | `None` | LLM model identifier (e.g., 'claude-sonnet-4-5-20250929') |
| `temperature` | number | null |  | `None` | LLM temperature (0.0-2.0) |
| `max_tokens` | integer | null |  | `None` | Maximum tokens in LLM response (256-200000) |
| `narrative_style` | string | null |  | `None` | Narrative style: descriptive, concise, dramatic, cinematic, etc. |
| `dialogue_style` | string | null |  | `None` | Dialogue style: natural, theatrical, formal, casual, etc. |
| `difficulty` | string | null |  | `None` | Game difficulty |
| `improvisation_level` | integer | null |  | `None` | AI improvisation level: 0=None, 1=Low, 2=Medium, 3=High, 4=Full |
| `agent_timeout` | number | null |  | `None` | Maximum seconds per agent call (> 0) |
| `fudge_rolls` | boolean | null |  | `None` | Whether DM can fudge dice rolls for narrative purposes |
| `model_profile` | string | null |  | `None` | Switch model quality profile. Updates all model settings and CC agent files at once. |
| `interaction_mode` | string | null |  | `None` | Switch interaction mode: 'classic' (text-only), 'narrated' (TTS + text), 'immersive' (TTS + STT). Takes effect immediately. |
| `reset_to_defaults` | boolean |  | `False` | Reset all settings to defaults |

### `dm20__start_claudmaster_session`

Start or resume a Claudmaster AI DM session.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `campaign_name` | string | ✓ |  | Name of the campaign to play |
| `module_id` | string | null |  | `None` | Optional D&D module to load |
| `session_id` | string | null |  | `None` | Session ID to resume (required if resume=True) |
| `resume` | boolean |  | `False` | Whether to resume an existing session |

### `dm20__end_claudmaster_session`

End or pause a Claudmaster AI DM session, saving all state.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `session_id` | string | ✓ |  | The session ID to end or pause |
| `mode` | string |  | `pause` | 'pause' to save for later, 'end' for final termination |
| `summary_notes` | string | null |  | `None` | Optional DM notes to save with the session |
| `campaign_path` | string | null |  | `None` | Optional path for disk persistence |

### `dm20__get_claudmaster_session_state`

Get the current state of a Claudmaster AI DM session.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `session_id` | string | ✓ |  | The session ID to query |
| `detail_level` | string |  | `standard` | Detail level: 'minimal', 'standard', or 'full' |
| `include_history` | boolean |  | `True` | Whether to include action history |
| `history_limit` | integer |  | `10` | Max number of history entries to return |

### `dm20__player_action`

Process a player action in the current Claudmaster session.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `session_id` | string | ✓ |  | The active session ID to process the action in |
| `action` | string | ✓ |  | The player's action as natural language text |
| `character_name` | string | null |  | `None` | Optional name of the character performing the action |
| `context` | string | null |  | `None` | Optional additional context about the action |

### `dm20__discover_adventures`

Discover D&D adventures by theme, keyword, level range, or storyline.

Search and browse official D&D 5e adventure modules from the 5etools
index. Results are grouped by storyline and presented without spoilers.

Empty query with no filters returns a summary of all available storylines.

Keyword mapping examples:
- "vampire", "gothic", "horror" → Ravenloft
- "school", "magic school" → Strixhaven
- "dragon", "cult" → Tyranny of Dragons
- "heist" → Keys from the Golden Vault, Waterdeep
- "space" → Spelljammer

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `query` | string |  | `''` | Keyword search (theme, name, etc.) |
| `level_min` | integer | null |  | `None` | Minimum character level filter |
| `level_max` | integer | null |  | `None` | Maximum character level filter |
| `storyline` | string | null |  | `None` | Filter by storyline |
| `limit` | integer |  | `10` | Maximum number of results |

### `dm20__load_adventure`

Load a D&D adventure module and integrate it with your campaign.

This tool orchestrates the complete adventure loading workflow:
1. Downloads and parses adventure content from 5etools (or uses cached version)
2. Creates a new campaign or uses the current one
3. Binds the module to the campaign for progress tracking
4. Auto-populates Chapter 1 entities (locations, NPCs, starting quest) to begin play

The tool respects spoiler boundaries: only Chapter 1 content is revealed.
Later chapters remain hidden until you progress through the adventure.

Examples:
- `load_adventure("CoS")` - Load Curse of Strahd into current campaign
- `load_adventure("LMoP", "Lost Mine Campaign")` - Create new campaign for Lost Mine of Phandelver
- `load_adventure("SCC-CK", populate_chapter_1=False)` - Load Strixhaven intro without auto-population

Common adventure IDs:
- CoS: Curse of Strahd
- LMoP: Lost Mine of Phandelver
- HotDQ: Hoard of the Dragon Queen
- PotA: Princes of the Apocalypse
- OotA: Out of the Abyss
- ToA: Tomb of Annihilation
- WDH: Waterdeep: Dragon Heist
- WDMM: Waterdeep: Dungeon of the Mad Mage
- BGDIA: Baldur's Gate: Descent into Avernus

Use the `discover_adventures` tool to search for more adventures by theme or level range.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `adventure_id` | string | ✓ |  | Adventure ID from 5etools (e.g., 'CoS', 'LMoP', 'SCC-CK') |
| `campaign_name` | string | null |  | `None` | Name for new campaign. If not provided, uses current campaign |
| `populate_chapter_1` | boolean |  | `True` | Auto-create Chapter 1 locations, NPCs, and starting quest |

### `dm20__export_character_sheet`

Export a character to a Markdown sheet file.

Generates a beautiful Markdown character sheet with YAML frontmatter
in the campaign's sheets/ directory. The sheet can be viewed in any
Markdown editor, with optional Meta-Bind support for Obsidian.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name_or_id` | string | ✓ |  | Character name, ID, or player name |
| `player_id` | string | null |  | `None` | Player ID for permission check (omit for single-player DM mode) |

### `dm20__sync_all_sheets`

Regenerate all character sheets for the current campaign.

Useful after bulk changes or to ensure all sheets are up to date.

_no parameters_

### `dm20__check_sheet_changes`

List pending player edits from character sheet files.

Shows changes detected from player-edited Markdown sheets that
are waiting for DM approval.

_no parameters_

### `dm20__approve_sheet_change`

Approve or reject pending player edits from a character sheet.

When approved, changes are applied to the character's JSON data.
When rejected, the sheet is regenerated from the current server data,
overwriting the player's edits.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `character_name` | string | ✓ |  | Character name to approve/reject changes for |
| `approve` | boolean |  | `True` | True to approve, False to reject |

### `dm20__export_pack`

Export campaign content as a portable compendium pack.

Creates a JSON pack file containing selected campaign entities (NPCs,
locations, quests, encounters).  Supports selective export by entity
type, location filter, or full campaign backup.

The pack is saved to the packs/ directory inside the data folder.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ |  | Name for the exported pack |
| `description` | string |  | `''` | Pack description |
| `author` | string |  | `''` | Pack author |
| `tags` | string | null |  | `None` | Comma-separated tags (e.g., 'horror,undead,ravenloft') |
| `entity_types` | string | null |  | `None` | Comma-separated entity types to include: npcs, locations, quests, encounters. Omit for all. |
| `location_filter` | string | null |  | `None` | Only include entities associated with this location (case-insensitive substring match) |
| `full_backup` | boolean |  | `False` | If true, export ALL entities plus game state and sessions as a full backup |

### `dm20__import_pack`

Import a compendium pack into the current campaign.

Loads a CompendiumPack JSON file and imports its entities (NPCs, locations,
quests, encounters) into the active campaign. Handles name conflicts via
the chosen conflict mode. Regenerates all entity IDs and re-links cross-references.

Use preview=true for a dry-run that shows what would happen without changing anything.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `file_path` | string | ✓ |  | Path to the pack JSON file to import |
| `conflict_mode` | string |  | `skip` | Conflict resolution: 'skip' (keep existing), 'overwrite' (replace), 'rename' (add suffix) |
| `preview` | boolean |  | `False` | If true, show what would be imported without making changes |
| `entity_filter` | string | null |  | `None` | Comma-separated entity types to import: npcs, locations, quests, encounters. Omit for all. |

### `dm20__list_packs`

List all available compendium packs in the packs directory.

Scans the packs/ directory for JSON pack files and returns their names,
descriptions, entity counts, and file paths.

_no parameters_

### `dm20__validate_pack`

Validate a compendium pack file without importing it.

Checks the pack for schema conformance, version compatibility, entity
count consistency, and required fields. Returns a detailed validation report.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `file_path` | string | ✓ |  | Path to the pack JSON file to validate |

### `dm20__party_knowledge`

Query what the party knows about the world.

Searches the party's collective knowledge — facts they have learned
through NPC interactions, observation, investigation, reading, and other
means. Returns matching facts with details on how they were learned.

Use with no arguments to list all known facts. Provide a topic to search
for specific knowledge. Optionally filter by source or acquisition method.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `topic` | string |  | `''` | Topic to search party knowledge about (e.g., 'dragon', 'Strahd', 'curse') |
| `source_filter` | string | null |  | `None` | Filter by knowledge source (e.g., NPC name) |
| `method_filter` | string | null |  | `None` | Filter by acquisition method: told_by_npc, observed, investigated, read, overheard, deduced, magical, common_knowledge |

### `dm20__import_from_dndbeyond`

Import a public D&D Beyond character into the current campaign.

Provide a D&D Beyond character URL (e.g., https://www.dndbeyond.com/characters/12345678)
or just the numeric character ID. The character must be set to Public on D&D Beyond.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `url_or_id` | string | ✓ |  | D&D Beyond character URL or numeric ID |
| `player_name` | string | null |  | `None` | Player name to assign to the character |

### `dm20__import_character_file`

Import a character from a local JSON file into the current campaign.

Currently supports D&D Beyond JSON format. Save the JSON from your browser's
developer tools (Network tab -> character request -> Response).

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `file_path` | string | ✓ |  | Path to the D&D Beyond JSON file |
| `player_name` | string | null |  | `None` | Player name to assign to the character |
| `source_format` | string |  | `dndbeyond` | Format of the JSON file |

### `dm20__send_private_message`

DM can send private messages to individual players via this tool.

Messages are stored in the session coordinator and can be retrieved
by the recipient player. Only visible to the specified recipient.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `player_id` | string | ✓ |  | Recipient player ID |
| `content` | string | ✓ |  | Message content to send privately |
| `sender_id` | string |  | `DM` | Sender player ID (typically the DM) |

### `dm20__start_party_mode`

Start the Party Mode web server for multi-player sessions.

Launches a background HTTP server that allows multiple players to connect
via their phones or browsers. Automatically generates authentication tokens
and QR codes for each player character in the current campaign.

Returns connection URLs and QR code file paths for each player.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `port` | integer |  | `8080` | Server port number |

### `dm20__stop_party_mode`

Stop the Party Mode web server and disconnect all players.

Gracefully shuts down the server and closes all WebSocket connections.

_no parameters_

### `dm20__get_party_status`

Get the current status of the Party Mode server.

Shows server info, connected players, and action queue stats.

_no parameters_

### `dm20__party_pop_action`

Pop the next pending player action from the Party Mode queue.

Returns the action details (player_id, action_id, text, timestamp) and
remaining queue count, or reports that the queue is empty.

_no parameters_

### `dm20__party_resolve_action`

Resolve a player action and broadcast the response to connected players.

After processing a player action (rolling dice, narrating outcome, updating state),
call this tool to push the response to the WebSocket broadcast queue.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `action_id` | string | ✓ |  | The action_id returned by party_pop_action |
| `narrative` | string | ✓ |  | The DM's narrative response to the player's action |
| `private_messages` | string | null |  | `None` | JSON object of player-specific private messages, e.g. {"player": "secret"} |
| `dm_notes` | string | null |  | `None` | DM-only notes (not sent to players) |

### `dm20__party_thinking`

Signal to players that the DM is preparing the next narrative.

Call this immediately after party_pop_action to give players instant
visual feedback (animated dots + message) while you think and generate
the response. The indicator disappears automatically when you call
party_resolve_action.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `message` | string | null |  | `None` | Short message shown to players, e.g. 'The Dungeon Master consults the ancient scrolls…' |

### `dm20__party_get_prefetch`

Retrieve a pre-generated narrative variant for a combat turn.

If the prefetch engine has a cached variant for this turn, returns a
refined narrative instantly (no main-model call needed). On cache miss,
falls back to full generation with the main model.

Call this right after party_thinking, before writing your own narrative.
If 'cached' is true in the response, use 'narrative' as your starting
point and adjust only the details that differ from actual game state.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `turn_id` | string | ✓ |  | Turn identifier — use the same format as the observer: 'round_{N}_{character_name}', e.g. 'round_3_Aria' |
| `outcome` | string | ✓ |  | Actual combat outcome: 'hit', 'miss', or 'critical' |
| `roll` | integer | null |  | `None` | The actual attack roll value |
| `damage` | integer | null |  | `None` | Damage dealt (for hit/critical) |
| `target_hp` | integer | null |  | `None` | Target's remaining HP after damage |

### `dm20__party_kick_player`

Kick a player from the Party Mode session.

Disconnects their WebSocket, revokes their token, and deactivates
them in the PC registry. They will need a new token to rejoin.

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `player_name` | string | ✓ |  | Player name or character ID to kick |

### `dm20__party_refresh_token`

Generate a new token and QR code for a player, invalidating their old token.

Use when a player needs a new connection link (lost QR code, security concern,
or after being kicked and readmitted).

| Param | Type | Req | Default | Description |
|---|---|---|---|---|
| `player_name` | string | ✓ |  | Player name or character ID to refresh token for |

### `dm20__check_for_updates`

Check if a newer version of dm20-protocol is available.

Compares the installed version with the latest on GitHub.
Returns update status, current/latest versions, and upgrade command if needed.
Call this at session start to notify the user about available updates.

_no parameters_

### `dm20__get_release_notes`

Fetch the latest release notes from the CHANGELOG.

Returns the most recent changelog entries (Unreleased + last released version)
from the GitHub repository. Use this to show users what's new.

_no parameters_

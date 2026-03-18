"""Tests for the anchor-based D2 diagram merger."""

from diagram_update.merger import check_removal_threshold, merge_diagrams, parse_d2


# --- parse_d2 tests ---


class TestParseD2:
    def test_extracts_simple_nodes(self) -> None:
        content = "api\ndb\nauth"
        parsed = parse_d2(content)
        assert parsed.node_keys == {"api", "db", "auth"}

    def test_extracts_nodes_with_labels(self) -> None:
        content = "api: API Server\ndb: Database"
        parsed = parse_d2(content)
        assert parsed.node_keys == {"api", "db"}

    def test_extracts_node_with_block(self) -> None:
        content = "api {\n  label: API\n  style.fill: blue\n}"
        parsed = parse_d2(content)
        assert "api" in parsed.node_keys
        assert parsed.node_spans["api"] == (0, 3)

    def test_extracts_edges(self) -> None:
        content = "api -> db\nauth -> db"
        parsed = parse_d2(content)
        assert ("api", "->", "db") in parsed.edge_tuples
        assert ("auth", "->", "db") in parsed.edge_tuples

    def test_extracts_edge_labels(self) -> None:
        content = "api -> db: reads from"
        parsed = parse_d2(content)
        key = ("api", "->", "db")
        assert key in parsed.edge_tuples
        assert parsed.edge_labels[key] == "reads from"

    def test_extracts_bidirectional_edges(self) -> None:
        content = "api <-> cache"
        parsed = parse_d2(content)
        assert ("api", "<->", "cache") in parsed.edge_tuples

    def test_skips_comments(self) -> None:
        content = "# this is a comment\napi\n# another comment\ndb"
        parsed = parse_d2(content)
        assert parsed.node_keys == {"api", "db"}

    def test_skips_empty_lines(self) -> None:
        content = "api\n\n\ndb"
        parsed = parse_d2(content)
        assert parsed.node_keys == {"api", "db"}

    def test_skips_config_lines(self) -> None:
        content = "vars: {\n  d2-config: {\n    layout-engine: elk\n  }\n}\ndirection: right\napi"
        parsed = parse_d2(content)
        # api should be found, config lines skipped
        assert "api" in parsed.node_keys

    def test_dotted_node_names(self) -> None:
        content = "src.api.handlers"
        parsed = parse_d2(content)
        assert "src.api.handlers" in parsed.node_keys

    def test_edge_line_indices(self) -> None:
        content = "api\ndb\napi -> db"
        parsed = parse_d2(content)
        assert parsed.edge_line_indices[("api", "->", "db")] == 2

    def test_nested_blocks(self) -> None:
        content = "api {\n  inner {\n    deep: val\n  }\n}"
        parsed = parse_d2(content)
        assert "api" in parsed.node_keys
        assert parsed.node_spans["api"] == (0, 4)


# --- merge_diagrams tests ---


class TestMergeDiagrams:
    def test_empty_old_returns_new(self) -> None:
        new = "api\ndb\napi -> db"
        assert merge_diagrams("", new) == new

    def test_whitespace_old_returns_new(self) -> None:
        new = "api\ndb\napi -> db"
        assert merge_diagrams("  \n  ", new) == new

    def test_identical_is_idempotent(self) -> None:
        content = "api\ndb\napi -> db"
        result = merge_diagrams(content, content)
        assert result == content

    def test_adds_new_nodes(self) -> None:
        old = "api\ndb\napi -> db"
        new = "api\ndb\ncache\napi -> db"
        result = merge_diagrams(old, new)
        assert "cache" in result
        assert "api" in result
        assert "db" in result

    def test_removes_deleted_nodes(self) -> None:
        old = "api\ndb\ncache\napi -> db"
        new = "api\ndb\napi -> db"
        result = merge_diagrams(old, new)
        assert "cache" not in result
        assert "api" in result
        assert "db" in result

    def test_adds_new_edges(self) -> None:
        old = "api\ndb\napi -> db"
        new = "api\ndb\napi -> db\ndb -> cache"
        result = merge_diagrams(old, new)
        assert "db -> cache" in result

    def test_removes_deleted_edges(self) -> None:
        old = "api\ndb\napi -> db\napi -> cache"
        new = "api\ndb\napi -> db"
        result = merge_diagrams(old, new)
        assert "api -> cache" not in result
        assert "api -> db" in result

    def test_updates_edge_labels(self) -> None:
        old = "api -> db: reads"
        new = "api -> db: writes"
        result = merge_diagrams(old, new)
        assert "api -> db: writes" in result
        assert "reads" not in result

    def test_preserves_ordering_of_unchanged_nodes(self) -> None:
        old = "auth\napi\ndb\nauth -> api\napi -> db"
        new = "auth\napi\ndb\nauth -> api\napi -> db"
        result = merge_diagrams(old, new)
        lines = result.splitlines()
        auth_idx = lines.index("auth")
        api_idx = lines.index("api")
        db_idx = lines.index("db")
        assert auth_idx < api_idx < db_idx

    def test_preserves_comments(self) -> None:
        old = "# Main services\napi\n# Database layer\ndb\napi -> db"
        new = "api\ndb\napi -> db"
        result = merge_diagrams(old, new)
        assert "# Main services" in result
        assert "# Database layer" in result

    def test_new_nodes_inserted_before_first_edge(self) -> None:
        old = "api\ndb\napi -> db"
        new = "api\ndb\ncache\napi -> db\napi -> cache"
        result = merge_diagrams(old, new)
        lines = result.splitlines()
        cache_idx = next(i for i, l in enumerate(lines) if l.strip() == "cache")
        edge_idx = next(i for i, l in enumerate(lines) if "api -> db" in l)
        assert cache_idx < edge_idx

    def test_new_edges_appended_at_end(self) -> None:
        old = "api\ndb\napi -> db"
        new = "api\ndb\napi -> db\ndb -> cache"
        result = merge_diagrams(old, new)
        lines = result.splitlines()
        assert lines[-1].strip() == "db -> cache"

    def test_removes_node_with_block(self) -> None:
        old = "api {\n  label: API Server\n}\ndb\napi -> db"
        new = "db"
        result = merge_diagrams(old, new)
        assert "api" not in result.lower().split("\n")[0] if result else True
        assert "API Server" not in result
        assert "db" in result

    def test_edge_label_removed(self) -> None:
        old = "api -> db: reads from"
        new = "api -> db"
        result = merge_diagrams(old, new)
        assert "api -> db" in result
        assert "reads from" not in result

    def test_preserves_layout_hints(self) -> None:
        old = "# layout hint: keep api on left\napi\ndb\napi -> db"
        new = "api\ndb\napi -> db"
        result = merge_diagrams(old, new)
        assert "layout hint" in result


# --- check_removal_threshold tests ---


class TestCheckRemovalThreshold:
    def test_no_removal_returns_false(self) -> None:
        old = "api\ndb\nauth"
        merged = "api\ndb\nauth"
        assert check_removal_threshold(old, merged) is False

    def test_small_removal_returns_false(self) -> None:
        old = "api\ndb\nauth\ncache\nqueue"
        merged = "api\ndb\nauth\ncache"  # 1/5 = 20% removed
        assert check_removal_threshold(old, merged) is False

    def test_large_removal_returns_true(self) -> None:
        old = "api\ndb\nauth\ncache\nqueue\nworker"
        merged = "api"  # 5/6 = 83% removed
        assert check_removal_threshold(old, merged) is True

    def test_exact_threshold_returns_false(self) -> None:
        # 80% exactly should not trigger (only > 80%)
        old = "a\nb\nc\nd\ne"
        merged = "a"  # 4/5 = 80%
        assert check_removal_threshold(old, merged) is False

    def test_above_threshold_returns_true(self) -> None:
        old = "a\nb\nc\nd\ne\nf"
        merged = "a"  # 5/6 = 83% removed
        assert check_removal_threshold(old, merged) is True

    def test_empty_old_returns_false(self) -> None:
        assert check_removal_threshold("", "api\ndb") is False

    def test_custom_threshold(self) -> None:
        old = "a\nb\nc\nd"
        merged = "a\nb"  # 50% removed
        assert check_removal_threshold(old, merged, threshold=0.4) is True
        assert check_removal_threshold(old, merged, threshold=0.6) is False

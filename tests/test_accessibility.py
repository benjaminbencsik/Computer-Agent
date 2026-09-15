from computer_agent.accessibility import Node, format_tree, search, walk


class FakeRect:
    def __init__(self, left, top, width, height):
        self.left = left
        self.top = top
        self.width = width
        self.height = height


class FakeElement:
    def __init__(self, name="", automation_id="", control_type="Pane", rect=None, children=None):
        self.Name = name
        self.AutomationId = automation_id
        self.ControlTypeName = control_type
        self.BoundingRectangle = rect
        self._children = children or []

    def GetChildren(self):
        return self._children


def test_walk_collects_named_nodes_with_geometry():
    tree = FakeElement(
        name="Window",
        control_type="Window",
        rect=FakeRect(0, 0, 800, 600),
        children=[
            FakeElement(name="OK", control_type="Button", rect=FakeRect(10, 20, 80, 30)),
            FakeElement(rect=FakeRect(5, 5, 5, 5)),  # unnamed, no automation id -> skipped
        ],
    )
    nodes = walk(tree, max_depth=4, max_nodes=200)
    assert [node.name for node in nodes] == ["Window", "OK"]
    assert nodes[1].center == (50, 35)


def test_walk_respects_max_depth_and_max_nodes():
    leaf = FakeElement(name="Leaf", rect=FakeRect(0, 0, 10, 10))
    mid = FakeElement(name="Mid", rect=FakeRect(0, 0, 10, 10), children=[leaf])
    root = FakeElement(name="Root", rect=FakeRect(0, 0, 10, 10), children=[mid])

    assert [n.name for n in walk(root, max_depth=0, max_nodes=200)] == ["Root"]
    assert [n.name for n in walk(root, max_depth=1, max_nodes=200)] == ["Root", "Mid"]
    assert len(walk(root, max_depth=4, max_nodes=1)) == 1


def test_format_tree_lists_indexed_descriptions():
    nodes = [Node("Button", "OK", "okBtn", 10, 20, 80, 30)]
    text = format_tree(nodes)
    assert text == '[0] Button "OK" id=okBtn at (50, 35)'


def test_format_tree_empty():
    assert "No named UI elements" in format_tree([])


def test_search_matches_by_automation_id_name_and_control_type():
    nodes = [
        Node("Button", "OK", "okBtn", 0, 0, 10, 10),
        Node("Edit", "Search box", "searchEdit", 0, 0, 10, 10),
    ]
    assert search(nodes, automation_id="okBtn") is nodes[0]
    assert search(nodes, name="search") is nodes[1]
    assert search(nodes, control_type="Edit") is nodes[1]
    assert search(nodes, name="nope") is None

# ========== TREE BUILDING ==========
def build_span_tree(spans: list[dict]) -> list[dict]:
    """
    Build hierarchical tree from flat list of spans.
    
    Returns list of root nodes, each with nested 'children' arrays.
    """
    if not spans:
        return []
    
    # Create lookup map: span_id -> span
    span_map = {s["span_id"]: dict(s) for s in spans}
    
    # Add empty children array to each span
    for span in span_map.values():
        span["children"] = []
    
    # Build tree by attaching children to parents
    roots = []
    for span in span_map.values():
        parent_id = span.get("parent_span_id")
        if parent_id and parent_id in span_map:
            # Has parent - attach to parent's children
            span_map[parent_id]["children"].append(span)
        else:
            # No parent (or parent not found) - it's a root
            roots.append(span)
    
    # Sort children by started_at (or sequence_index)
    def sort_children(node):
        if node.get("children"):
            # Sort by started_at timestamp
            node["children"].sort(key=lambda x: x.get("started_at", ""))
            # Recursively sort grandchildren
            for child in node["children"]:
                sort_children(child)
    
    for root in roots:
        sort_children(root)
    
    # Sort roots by started_at
    roots.sort(key=lambda x: x.get("started_at", ""))
    
    return roots


# ========== DEPTH MAP ==========
def compute_depth_map(spans: list[dict]) -> dict[str, int]:
    """
    Calculate depth of each span in tree.
    
    Returns: {"span-1": 0, "span-2": 1, "span-3": 1, ...}
    """
    depth_map = {}
    
    # Create parent lookup
    parent_lookup = {s["span_id"]: s.get("parent_span_id") for s in spans}
    
    def get_depth(span_id: str) -> int:
        """Recursively calculate depth"""
        if span_id in depth_map:
            return depth_map[span_id]
        
        parent_id = parent_lookup.get(span_id)
        if not parent_id:
            # Root node
            depth_map[span_id] = 0
            return 0
        
        # Depth = parent's depth + 1
        parent_depth = get_depth(parent_id)
        depth_map[span_id] = parent_depth + 1
        return depth_map[span_id]
    
    # Calculate depth for all spans
    for span in spans:
        get_depth(span["span_id"])
    
    return depth_map


# ========== HELPER: Apply depth to spans ==========
def apply_depth_to_spans(spans: list[dict]) -> list[dict]:
    """
    Add 'depth' field to each span based on tree structure.
    Modifies spans in-place and returns them.
    """
    depth_map = compute_depth_map(spans)
    
    for span in spans:
        span["depth"] = depth_map.get(span["span_id"], 0)
    
    return spans
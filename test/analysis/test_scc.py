import pytest
import networkx as nx
from cpnpy.analysis.scc import build_scc_graph

def test_scc_single_component():
    """Verify that a simple cycle is collapsed into one SCC."""
    # Build a simple cycle in a DiGraph
    RG = nx.DiGraph()
    RG.add_edge(0, 1)
    RG.add_edge(1, 0)
    
    SG = build_scc_graph(RG)
    
    # Condensation collapses SCCs into single nodes
    assert len(SG.nodes) == 1
    # The member list should contain both original nodes
    assert SG.nodes[0]['members'] == {0, 1}

def test_scc_multiple_components():
    """Verify that multiple components are correctly identified and linked."""
    # 0 <-> 1  -> 2
    RG = nx.DiGraph()
    RG.add_edge(0, 1)
    RG.add_edge(1, 0)
    RG.add_edge(1, 2)
    
    SG = build_scc_graph(RG)
    
    # Two SCCs: {0, 1} and {2}
    assert len(SG.nodes) == 2
    # There should be an edge from the SCC containing 1 to the SCC containing 2
    
    scc_with_1 = None
    scc_with_2 = None
    for n in SG.nodes:
        if 1 in SG.nodes[n]['members']:
            scc_with_1 = n
        if 2 in SG.nodes[n]['members']:
            scc_with_2 = n
            
    assert scc_with_1 is not None
    assert scc_with_2 is not None
    assert SG.has_edge(scc_with_1, scc_with_2)

if __name__ == "__main__":
    pytest.main([__file__])

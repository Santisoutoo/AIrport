import json
import networkx as nx
import plotly.graph_objects as go

CONFIGURATION = 'West'

with open("taxiways.json", "r") as file:
    taxiways_data = json.load(file)

G = nx.Graph()

# Get taxiway data
taxiways = taxiways_data["configurations"][CONFIGURATION]["taxiways"]

# Graph
for taxiway in taxiways:
    name = taxiway["name"]
    lat, lon = taxiway["coordinates"]
    
    # In order to not get a specular image we invert the coordenates
    G.add_node(name, pos=(lon, lat))  
    
    for connection in taxiway["connections"]:
        G.add_edge(name, connection)

# Visualization
pos = nx.get_node_attributes(G, 'pos')
edge_x = []
edge_y = []
for edge in G.edges():
    x0, y0 = pos[edge[0]]
    x1, y1 = pos[edge[1]]
    edge_x.extend([x0, x1, None])
    edge_y.extend([y0, y1, None])

edge_trace = go.Scatter(
    x=edge_x, y=edge_y,
    line=dict(width=1, color="gray"),
    hoverinfo="none",
    mode="lines"
)

node_x = [pos[node][0] for node in G.nodes()]
node_y = [pos[node][1] for node in G.nodes()]
node_text = list(G.nodes())

node_trace = go.Scatter(
    x=node_x, y=node_y,
    mode="markers+text",
    marker=dict(size=10, color="blue"),
    text=node_text,
    textposition="top center",
    hoverinfo="text"
)

fig = go.Figure(data=[edge_trace, node_trace])

fig.update_layout(
    title="Taxiways",
    showlegend=False,
    hovermode="closest",
    margin=dict(b=20, l=5, r=5, t=40),
    xaxis=dict(title="Longitude", showgrid=False, zeroline=False),
    yaxis=dict(title="Latitude", showgrid=False, zeroline=False, scaleanchor="x")
)

print("CHECK YOUR BROSER TO SEE THE GRAPH GENERATED")
fig.show()
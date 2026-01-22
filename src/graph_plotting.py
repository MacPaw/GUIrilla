import matplotlib.pyplot as plt
import networkx as nx
import PIL
import helpers.element_graph as Graph
import os
import helpers.files as files

from matplotlib.offsetbox import OffsetImage, AnnotationBbox


# Process the nodes
def process_node(G: nx.Graph, node: Graph.Vertice, images: dict):
    G.add_node(node.image_name, image=images[node.image_name])
    for edge in node.edges:
        G.add_edge(edge.in_vertice.image_name, edge.out_vertice.image_name)
        process_node(G, edge.out_vertice, images)


# Draw the graph
def draw_plot(node: Graph.Vertice, path: str):
    print("Drawing the graph...")
    # Load images
    image_path = os.path.join(path, "graph", "images")
    images = {}
    for file in os.listdir(image_path):
        if file.endswith(".DS_Store"):
            continue
        if file.endswith(".png"):
            # Load images
            file_path = os.path.join(image_path, file)
            images[file] = PIL.Image.open(file_path)

    plt.figure(1, figsize=(100, 100), dpi=60)

    # Generate the graph
    G = nx.DiGraph()

    # Process the nodes
    process_node(G, node, images)

    # Set the positions of the nodes
    pos = nx.spring_layout(G, k=0.8, iterations=200, scale=3.0)

    # Draw the graph
    fig, ax = plt.subplots(figsize=(20, 20))

    # Set the options for the graph
    options = {
        "node_color": "white",  # color of node
        "node_size": 2700,  # size of node
        "width": 1,  # line width of edges
        "arrowstyle": "-|>",  # array style for directed graph
        "arrowsize": 15,  # size of arrow
        "edge_color": "blue",  # edge color
    }

    nx.draw(G, pos, ax=ax, with_labels=False, arrows=True, **options)

    # Add images to the nodes
    for node in G.nodes(data=True):
        img = OffsetImage(node[1]["image"], zoom=0.035)
        ab = AnnotationBbox(img, pos[node[0]], frameon=False)
        ax.add_artist(ab)

    # Ensure proper spacing and aspect ratio
    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
    ax.set_aspect("equal")

    # Save the figure before showing it
    plt.savefig(os.path.join(path, "graph", "graph.svg"), format="svg", dpi=1200)


# print the graph
def print_graph(node: Graph.Vertice, output_folder: str):
    print("Printing the graph...")
    # drop last extension
    if node.image_name is None or len(node.image_name) == 0:
        print("Node image name is empty")

    vertice_name, _ = os.path.splitext(node.image_name)

    if vertice_name is None or len(vertice_name) == 0:
        vertice_name = "root"
        print("Vertice name is empty")

    output_file = os.path.join(output_folder, "graph", "data.json")
    files.store_data_to_file(node, output_file)
    print(f"Graph is stored to {output_file}")

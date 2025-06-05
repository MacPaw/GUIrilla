import os
import shutil
import json
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

# Setup Jinja2 environment
env = Environment(loader=FileSystemLoader('templates'))
index_template = env.get_template('index.html')
app_template = env.get_template('app.html')
images_template = env.get_template('images.html')

def generate_dashboard(output_folder: str, report_data_path: str, total_time_str: str):
    print("----------------------------------------------")
    print("Generating dashboard for application path: ", output_folder)
    print("Total time: ", total_time_str)
    # Create/clean dashboard directory

    dashboard_dir = os.path.join(output_folder, 'dashboard')
    if os.path.exists(dashboard_dir):
        shutil.rmtree(dashboard_dir)
    os.makedirs(dashboard_dir, exist_ok=True)

    report_data = json.load(open(report_data_path))
    report_items = report_data['items']
    applications = []

    for _, report_item in report_items.items():
        app_name = report_item['app_name']
        app_bundle_name = report_item['app_bundle_id']
        app_folder = os.path.join(output_folder, app_bundle_name)
        graph_folder = os.path.join(app_folder, 'graph')
        if os.path.isdir(graph_folder):
            print("Graph folder: ", graph_folder)   
            data_json = os.path.join(graph_folder, 'data.json')
            graph_svg = os.path.join(graph_folder, 'graph.svg')
            images_dir = os.path.join(graph_folder, 'images')
            images, last_modified = [], ''

            if os.path.exists(data_json) and os.path.exists(graph_svg) and os.path.exists(images_dir) and 'elapsed_time_str' in report_item:
                images = [img for img in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, img))]
                last_modified = datetime.fromtimestamp(os.path.getmtime(data_json)).strftime('%Y-%m-%d %H:%M:%S')
                applications.append({
                    'name': app_name,
                    'bundle_name': app_bundle_name,
                    'data_json': os.path.join(app_name, 'data.json'),
                    'graph_svg': os.path.join(app_name, 'graph.svg'),
                    'images': os.path.join(app_name, 'images.html'),
                    'last_modified': last_modified,
                    'processing_time': report_item['elapsed_time_str']
                })

            # Create application directory in dashboard
            app_dashboard_dir = os.path.join(dashboard_dir, app_bundle_name)
            os.makedirs(app_dashboard_dir, exist_ok=True)

            # Generate images.html
            if images:
                images_root = os.path.join(graph_folder, 'images')
                images_page = images_template.render(app_name=app_name, image_root=images_root,  images=images)
                with open(os.path.join(app_dashboard_dir, 'images.html'), 'w') as f:
                    f.write(images_page)

            # Generate app index page
            if last_modified and applications:
                app_page = app_template.render(app=applications[-1], last_modified=last_modified, app_root=graph_folder)
                with open(os.path.join(app_dashboard_dir, 'index.html'), 'w') as f:
                    f.write(app_page)

    # Generate main index.html
    index_page = index_template.render(applications=applications, total_time_str=total_time_str)
    with open(os.path.join(dashboard_dir, 'index.html'), 'w') as f:
        f.write(index_page)

    print("Dashboard generated successfully in the 'dashboard' directory.")


if __name__ == "__main__":
    report_file_path = os.path.join("./", "completed_app_report.json")
    with open(report_file_path, 'r') as f:
        report_data = json.load(f)
    generate_dashboard("./output/2025-02-11_20-18-15", report_data, "00:05:28")

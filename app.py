from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
import os
import json
import csv
from io import StringIO
import numpy as np
from backend import (
    build_gene_receptor_ligand_table,
    fuzzy_search_kegg_disease
)

# Initialize Flask app
app = Flask(__name__)

# Ensure the uploads and outputs folder exists
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# Store recent searches in memory (in production, use a database)
recent_searches = []
MAX_RECENT_SEARCHES = 10

# Route: Home Page
@app.route('/')
def home():
    return render_template('index.html')

# Route: Get Disease Suggestions
@app.route('/suggest', methods=['POST'])
def suggest():
    data = request.get_json()
    disease_name = data.get('disease_name')

    if not disease_name:
        return jsonify({"error": "No disease name provided"}), 400

    # Get fuzzy matched suggestions
    suggestions = fuzzy_search_kegg_disease(disease_name)
    return jsonify(suggestions)

# Route: Get Recent Searches
@app.route('/recent_searches', methods=['GET'])
def get_recent_searches():
    return jsonify(recent_searches)

# Route: Process Disease Name with streaming
@app.route('/process_stream', methods=['POST'])
def process_stream():
    data = request.get_json()
    disease_name = data.get('disease_name')

    if not disease_name:
        return jsonify({"error": "No disease name provided"}), 400
    
    # Add to recent searches
    if disease_name not in recent_searches:
        recent_searches.insert(0, disease_name)
        if len(recent_searches) > MAX_RECENT_SEARCHES:
            recent_searches.pop()

    def generate():
        """Generator function for streaming results"""
        all_results = []
        
        def progress_callback(current, total, gene_name):
            # Send progress update
            progress_data = {
                'type': 'progress',
                'current': current,
                'total': total,
                'gene': gene_name,
                'percentage': int((current / total) * 100)
            }
            yield f"data: {json.dumps(progress_data)}\n\n"
        
        # Start processing
        yield f"data: {json.dumps({'type': 'start', 'message': 'Starting to process...'})}\n\n"
        
        try:
            table_data = build_gene_receptor_ligand_table(
                disease_name, 
                progress_callback=lambda c, t, g: all_results.append(progress_callback(c, t, g))
            )
            
            # Send all progress updates
            for progress_update in all_results:
                yield next(progress_update)
            
            # If no data found, try fuzzy search
            if not table_data:
                suggestions = fuzzy_search_kegg_disease(disease_name)
                yield f"data: {json.dumps({'type': 'error', 'message': 'No exact match found', 'suggestions': suggestions})}\n\n"
            else:
                # Send results
                yield f"data: {json.dumps({'type': 'complete', 'data': table_data})}\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# Route: Process Disease Name (non-streaming fallback)
@app.route('/process', methods=['POST'])
def process():
    data = request.get_json()
    disease_name = data.get('disease_name')

    if not disease_name:
        return jsonify({"error": "No disease name provided"}), 400
    
    # Add to recent searches
    if disease_name not in recent_searches:
        recent_searches.insert(0, disease_name)
        if len(recent_searches) > MAX_RECENT_SEARCHES:
            recent_searches.pop()

    # Call backend function to build the data
    table_data = build_gene_receptor_ligand_table(disease_name)
    
    # If no data found, try fuzzy search
    if not table_data:
        suggestions = fuzzy_search_kegg_disease(disease_name)
        return jsonify({"error": "No exact match found", "suggestions": suggestions}), 404

    return jsonify(table_data)

# Route: Export to CSV
@app.route('/export_csv', methods=['POST'])
def export_csv():
    data = request.get_json()
    table_data = data.get('data')
    disease_name = data.get('disease_name', 'results')
    
    if not table_data:
        return jsonify({"error": "No data to export"}), 400
    
    # Create CSV in memory
    output = StringIO()
    if table_data:
        headers = list(table_data[0].keys())
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(table_data)
    
    # Save to file
    filename = f"{disease_name.replace(' ', '_')}_results.csv"
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        f.write(output.getvalue())
    
    return send_file(filepath, as_attachment=True, download_name=filename)

# Add this section to run the Flask app when the script is executed
if __name__ == '__main__':
    app.run(debug=True, threaded=True)

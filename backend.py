import requests
import pandas as pd
import xml.etree.ElementTree as ET
import concurrent.futures
import time
import logging
from io import StringIO
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import tempfile
from fuzzywuzzy import process, fuzz
from functools import wraps

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Retry decorator
def retry_on_failure(max_retries=3, delay=1):
    """Decorator to retry API calls on failure"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        return result
                    if attempt < max_retries - 1:
                        logger.warning(f"{func.__name__} returned None, retrying... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"{func.__name__} failed: {e}, retrying... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
                        return None
            return None
        return wrapper
    return decorator

# Timeout wrapper
def with_timeout(timeout_seconds=30):
    """Decorator to add timeout to functions"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Function {func.__name__} failed: {e}")
                return None
        return wrapper
    return decorator

def fuzzy_search_kegg_disease(disease_name, limit=5):
    """Search KEGG for diseases matching the input using fuzzy matching"""
    logger.info(f"Fuzzy searching for disease: {disease_name}")
    base_url = "http://rest.kegg.jp/list/disease"
    try:
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200:
            all_diseases = []
            for line in response.text.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    disease_id = parts[0]
                    disease_desc = parts[1]
                    all_diseases.append({
                        'id': disease_id,
                        'name': disease_desc
                    })
            
            disease_names = [d['name'] for d in all_diseases]
            matches = process.extract(disease_name, disease_names, scorer=fuzz.token_set_ratio, limit=limit)
            
            suggestions = []
            for match_name, score in matches:
                if score > 60:
                    disease_id = next(d['id'] for d in all_diseases if d['name'] == match_name)
                    suggestions.append({
                        'name': match_name,
                        'id': disease_id,
                        'score': score
                    })
            
            logger.info(f"Found {len(suggestions)} suggestions for '{disease_name}'")
            return suggestions
    except Exception as e:
        logger.error(f"Error in fuzzy search: {e}")
    
    return []

@retry_on_failure(max_retries=3, delay=1)
def retrieve_kegg_disease_id(disease_name):
    """Retrieve KEGG disease ID based on the disease name"""
    logger.info(f"Retrieving KEGG disease ID for: {disease_name}")
    base_url = f"http://rest.kegg.jp/find/disease/{disease_name}"
    response = requests.get(base_url, timeout=10)
    if response.status_code == 200 and response.text.strip():
        diseases = response.text.strip().split("\n")
        if diseases:
            disease_id = diseases[0].split("\t")[0]
            logger.info(f"Found KEGG disease ID: {disease_id}")
            return disease_id
    logger.warning(f"No KEGG disease ID found for: {disease_name}")
    return None

@retry_on_failure(max_retries=3, delay=1)
def retrieve_kegg_pathway_by_disease_id(disease_id):
    """Retrieve pathways from KEGG based on disease ID"""
    logger.info(f"Retrieving pathways for disease ID: {disease_id}")
    base_url = f"http://rest.kegg.jp/link/pathway/{disease_id}"
    response = requests.get(base_url, timeout=10)
    if response.status_code == 200 and response.text.strip():
        pathways = response.text.strip().split("\n")
        pathway_list = [{'pathway_id': path.split("\t")[1]} for path in pathways if 'hsa' in path]
        logger.info(f"Found {len(pathway_list)} pathways")
        return pathway_list
    logger.warning(f"No pathways found for disease ID: {disease_id}")
    return []

@retry_on_failure(max_retries=3, delay=1)
def retrieve_kegg_pathway_details(pathways):
    """Retrieve detailed information about pathways from KEGG"""
    pathway_details = []
    for pathway in pathways:
        pathway_id = pathway['pathway_id']
        logger.info(f"Retrieving pathway details for: {pathway_id}")
        kgml_url = f"http://rest.kegg.jp/get/{pathway_id}/kgml"
        response = requests.get(kgml_url, timeout=10)
        if response.status_code == 200:
            pathway_genes = parse_kgml(response.content)
            pathway_details.append({
                'pathway_id': pathway_id,
                'genes': pathway_genes
            })
            logger.info(f"Found {len(pathway_genes)} genes in pathway {pathway_id}")
    return pathway_details

def parse_kgml(kgml_data):
    """Parse KGML for genes and proteins; capture KEGG gene id from entry@name."""
    root = ET.fromstring(kgml_data)
    genes_proteins = []
    for entry in root.findall('entry'):
        if entry.get('type') in ('gene', 'protein'):
            graphics = entry.find('graphics')
            if graphics is None:
                continue

            gene_label = graphics.get('name')
            if not gene_label:
                continue

            # This is the KEGG identifier like "hsa:2099 hsa:xxxx" sometimes space-separated
            kegg_gene_name = entry.get('name')  # e.g. "hsa:2099"
            if kegg_gene_name:
                kegg_gene_id = kegg_gene_name.split()[0].strip()
            else:
                kegg_gene_id = None

            genes_proteins.append({
                'name': gene_label.split(",")[0].strip(),  # symbol-like label
                'kegg_gene_id': kegg_gene_id
            })
    return genes_proteins


@retry_on_failure(max_retries=2, delay=0.5)
def query_protein_info_uniprot(uniprot_id):
    """Query protein name and functional role from UniProt"""
    logger.info(f"Querying UniProt for: {uniprot_id}")
    uniprot_api_url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.xml"
    response = requests.get(uniprot_api_url, timeout=10)
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        ns = {'ns': 'http://uniprot.org/uniprot'}
        
        protein_name = root.find(".//ns:recommendedName/ns:fullName", ns)
        protein_name = protein_name.text if protein_name is not None else "Protein name not available"
        
        functional_role = "Functional role not available"
        comment = root.find(".//ns:comment[@type='function']/ns:text", ns)
        if comment is not None:
            functional_role = comment.text
        
        pdb_ids = []
        for pdb in root.findall(".//ns:dbReference[@type='PDB']", ns):
            pdb_id = pdb.get('id')
            method = pdb.find("ns:property[@type='method']", ns)
            method_val = method.get('value') if method is not None else None
            resolution = pdb.find("ns:property[@type='resolution']", ns)
            resolution_val = resolution.get('value') if resolution is not None else "N/A"
            pdb_ids.append({'id': pdb_id, 'method': method_val, 'resolution': resolution_val})
        
        ranked_pdb_ids = sorted(pdb_ids, key=lambda x: (x['method'] != "X-ray", float(x['resolution'].replace("A", "")) if x['resolution'] != "N/A" else float('inf')))
        top3_pdb_ids = [entry['id'] for entry in ranked_pdb_ids[:3]]
        
        return protein_name, functional_role, top3_pdb_ids
    
    logger.warning(f"Failed to retrieve UniProt data for {uniprot_id}")
    return "Protein name not available", "Functional role not available", []

@retry_on_failure(max_retries=2, delay=0.5)
def query_gene_name_and_id_uniprot(gene_name):
    """Query UniProt for gene name and ID"""
    logger.info(f"Querying UniProt for gene: {gene_name}")
    uniprot_api_url = f"https://rest.uniprot.org/uniprotkb/search?query={gene_name}+AND+organism_id:9606&format=json"
    response = requests.get(uniprot_api_url, timeout=10)
    if response.status_code == 200:
        data = response.json()
        if 'results' in data and data['results']:
            entry = data['results'][0]
            gene_name = entry.get('genes', [{}])[0].get('geneName', {}).get('value', 'N/A')
            uniprot_id = entry.get('primaryAccession', 'N/A')
            return gene_name, uniprot_id
    return 'N/A', 'N/A'

@retry_on_failure(max_retries=2, delay=0.5)
def query_receptors_uniprot(gene_name):
    """Query receptors from UniProt"""
    uniprot_api_url = f"https://rest.uniprot.org/uniprotkb/search?query={gene_name}+AND+organism_id:9606&format=json"
    response = requests.get(uniprot_api_url, timeout=10)
    if response.status_code == 200:
        data = response.json()
        receptors = []
        if 'results' in data and data['results']:
            for result in data['results']:
                protein_description = result.get('proteinDescription', {})
                recommended_name = protein_description.get('recommendedName', {}).get('fullName', {}).get('value', 'N/A')
                if 'comments' in result:
                    for comment in result['comments']:
                        if comment.get('commentType') == 'FUNCTION':
                            texts = comment.get('texts', [])
                            if texts and 'receptor' in texts[0].get('value', '').lower():
                                receptors.append(recommended_name)
        unique_receptors = list(set(receptors))
        return [rec.strip() for rec in unique_receptors if rec != 'N/A']
    return []

@retry_on_failure(max_retries=2, delay=0.5)
def get_gene_id_pubchem(gene_symbol):
    """Get gene ID from PubChem"""
    time.sleep(0.25)
    logger.info(f"Querying PubChem for gene symbol: {gene_symbol}")
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/gene/genesymbol/{gene_symbol}/summary/JSON"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'GeneSummaries' in data and 'GeneSummary' in data['GeneSummaries']:
                gene_id = data['GeneSummaries']['GeneSummary'][0]['GeneID']
                logger.info(f"Found PubChem gene ID: {gene_id} for {gene_symbol}")
                return gene_id
        logger.warning(f"No gene ID found in PubChem for: {gene_symbol}")
    except Exception as e:
        logger.error(f"Error querying PubChem for {gene_symbol}: {e}")
    return None

@retry_on_failure(max_retries=2, delay=0.5)
def get_bioactivity_data(gene_id):
    """Get bioactivity data from PubChem - CORRECTED INDICES"""
    time.sleep(0.25)
    logger.info(f"Querying PubChem bioactivity for gene ID: {gene_id}")
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/gene/geneid/{gene_id}/concise/JSON"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and response.headers.get('Content-Type', '').startswith('application/json'):
            data = response.json()
            bioactivity_data = []
            rows = data.get('Table', {}).get('Row', [])
            
            # Process top 20 rows for better chance of finding active compounds
            for row in rows[:20]:
                try:
                    # PubChem API structure:
                    # [0]=AID, [1]=SID, [2]=CID, [3]=Activity Outcome
                    # [4]=Target, [5]=Activity Name, [6]=Qualifier, [7]=Activity Value [uM]
                    
                    activity_outcome = str(row['Cell'][3]).strip()
                    cid = str(row['Cell'][2]).strip()
                    potency_str = str(row['Cell'][7]).strip()  # CORRECT INDEX: 7 not 5!
                    
                    # Only include "Active" compounds with valid potency
                    if activity_outcome != "Active":
                        continue
                    
                    if not potency_str or potency_str == '':
                        continue
                    
                    potency = float(potency_str)
                    if potency > 0:
                        bioactivity_data.append({'CID': cid, 'Potency': potency})
                        
                except (ValueError, IndexError, KeyError, TypeError):
                    continue
            
            logger.info(f"Found {len(bioactivity_data)} active ligands for gene ID {gene_id}")
            return bioactivity_data
        else:
            logger.warning(f"Invalid response for gene ID {gene_id}: status={response.status_code}")
    except Exception as e:
        logger.error(f"Error getting bioactivity data for gene ID {gene_id}: {e}")
    return []

@retry_on_failure(max_retries=2, delay=0.5)
def get_compound_name(cid):
    """Get compound name from PubChem"""
    time.sleep(0.25)
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/Title/JSON"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data['PropertyTable']['Properties'][0]['Title']
    except Exception as e:
        logger.error(f"Error getting compound name for CID {cid}: {e}")
    return f"Compound_{cid}"

def process_gene(gene_name, progress_callback=None):
    """Process each gene - main data gathering function"""
    try:
        logger.info(f"Processing gene: {gene_name}")

        # Always initialize these so they exist in all branches
        ligands_struct = []
        ligands = []

        # Query UniProt for receptor and gene ID
        uniprot_gene_name, uniprot_id = query_gene_name_and_id_uniprot(gene_name)
        receptors = query_receptors_uniprot(gene_name)

        # Query PubChem for gene ID and ligands
        gene_id = get_gene_id_pubchem(gene_name)

        if gene_id:
            bioactivity_data = get_bioactivity_data(gene_id)
            if bioactivity_data:
                sorted_ligands = sorted(bioactivity_data, key=lambda x: x['Potency'])[:5]

                for ligand in sorted_ligands:
                    cid = str(ligand["CID"])
                    potency = float(ligand["Potency"])
                    name = get_compound_name(cid)

                    ligands.append(f"{name} ({potency} uM)")
                    ligands_struct.append({"cid": cid, "name": name, "potency_um": potency})
            else:
                ligands = ["No ligand data available"]
                # ligands_struct stays []
                logger.warning(f"No bioactivity data found for gene {gene_name} (gene_id: {gene_id})")
        else:
            ligands = ["No gene ID found"]
            # ligands_struct stays []
            logger.warning(f"No PubChem gene ID found for {gene_name}")

        # Query for protein name, functional role, and PDB IDs
        if uniprot_id != "N/A":
            protein_name, functional_role, pdb_ids = query_protein_info_uniprot(uniprot_id)
        else:
            protein_name, functional_role, pdb_ids = "Protein name not available", "Functional role not available", []

        pdb_id_str = ', '.join(pdb_ids) if pdb_ids else "No PDB IDs"

        result = {
            'Gene Name': gene_name,
            'Gene ID': gene_id if gene_id else "N/A",
            'UniProt ID': uniprot_id,
            'Protein Name': protein_name,
            'PDB ID': pdb_id_str,
            'Receptors (Interacting)': ', '.join(receptors) if receptors else "No receptor interaction",
            'Functional Role': functional_role,
            'Ligands': '; '.join(ligands) if ligands else "No ligand data available",
            'ligands_struct': ligands_struct,   # ALWAYS present now
        }

        logger.info(f"Successfully processed gene: {gene_name}")
        return result

    except Exception as e:
        logger.error(f"Error processing gene {gene_name}: {e}")
        return {
            'Gene Name': gene_name,
            'Gene ID': "Error",
            'UniProt ID': "Error",
            'Protein Name': "Error processing gene",
            'PDB ID': "Error",
            'Receptors (Interacting)': "Error",
            'Functional Role': "Error",
            'Ligands': "Error",
            'ligands_struct': [],              # also always present here
        }

def build_gene_receptor_ligand_table(disease_name, progress_callback=None):
    """Main function to build the gene/receptor/ligand table"""
    logger.info(f"Building table for disease: {disease_name}")

    # Retrieve KEGG data
    disease_id = retrieve_kegg_disease_id(disease_name)
    if not disease_id:
        logger.warning(f"No KEGG data found for disease: {disease_name}")
        return []

    pathways = retrieve_kegg_pathway_by_disease_id(disease_id)
    if not pathways:
        logger.warning(f"No pathways found for disease: {disease_name}")
        return []

    kegg_data = retrieve_kegg_pathway_details(pathways)
    if not kegg_data:
        logger.warning(f"No pathway details found for disease: {disease_name}")
        return []

    # genes becomes a list of dicts with symbol + kegg_gene_id
    genes = []
    for pathway in kegg_data:
        for g in pathway["genes"]:
            genes.append({
                "symbol": g["name"].split(",")[0].strip(),
                "kegg_gene_id": g.get("kegg_gene_id")
            })

    logger.info(f"Found {len(genes)} genes to process")

    # Process genes with progress tracking
    table_data = []
    total_genes = len(genes)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_gene = {executor.submit(process_gene, g["symbol"]): g for g in genes}

        for i, future in enumerate(concurrent.futures.as_completed(future_to_gene)):
            g = future_to_gene[future]  # dict: {"symbol": ..., "kegg_gene_id": ...}
            try:
                result = future.result()

                # Inject KEGG gene id into the result row for ETL use
                result["kegg_gene_id"] = g.get("kegg_gene_id")

                table_data.append(result)

                if progress_callback:
                    # progress_callback expects a gene name string
                    progress_callback(i + 1, total_genes, g["symbol"])

            except Exception as e:
                logger.error(f"Exception for gene {g.get('symbol')}: {e}")

    logger.info(f"Completed processing {len(table_data)} genes")
    return table_data


def query_kegg(disease_name):
    """Query KEGG for disease information"""
    disease_id = retrieve_kegg_disease_id(disease_name)
    if disease_id:
        pathways = retrieve_kegg_pathway_by_disease_id(disease_id)
        if pathways:
            pathway_details = retrieve_kegg_pathway_details(pathways)
            return pathway_details
    return None

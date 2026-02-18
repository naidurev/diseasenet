import requests
import xml.etree.ElementTree as ET
import concurrent.futures
import time
import logging
from rapidfuzz import process, fuzz
from functools import wraps

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retry_on_failure(max_retries=3, delay=1):
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

def with_timeout(timeout_seconds=30):
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
            for match_name, score, _ in matches:
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
    root = ET.fromstring(kgml_data)
    genes_proteins = []
    seen = set()
    for entry in root.findall('entry'):
        if entry.get('type') in ('gene', 'protein'):
            graphics = entry.find('graphics')
            if graphics is None:
                continue

            gene_label = graphics.get('name')
            if not gene_label:
                continue

            gene_symbol = gene_label.split(",")[0].strip()
            if gene_symbol in seen:
                continue
            seen.add(gene_symbol)

            kegg_gene_name = entry.get('name')
            if kegg_gene_name:
                kegg_gene_id = kegg_gene_name.split()[0].strip()
            else:
                kegg_gene_id = None

            genes_proteins.append({
                'name': gene_symbol,
                'kegg_gene_id': kegg_gene_id
            })
    return genes_proteins


@retry_on_failure(max_retries=2, delay=0.5)
def query_protein_info_uniprot(uniprot_id):
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
    time.sleep(0.25)
    logger.info(f"Querying PubChem bioactivity for gene ID: {gene_id}")
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/gene/geneid/{gene_id}/concise/JSON"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and response.headers.get('Content-Type', '').startswith('application/json'):
            data = response.json()
            bioactivity_data = []
            rows = data.get('Table', {}).get('Row', [])
            
            for row in rows[:20]:
                try:
                    activity_outcome = str(row['Cell'][3]).strip()
                    cid = str(row['Cell'][2]).strip()
                    potency_str = str(row['Cell'][7]).strip()
                    
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
    try:
        logger.info(f"Processing gene: {gene_name}")

        ligands_struct = []
        ligands = []

        uniprot_gene_name, uniprot_id = query_gene_name_and_id_uniprot(gene_name)
        receptors = query_receptors_uniprot(gene_name)

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
                logger.warning(f"No bioactivity data found for gene {gene_name} (gene_id: {gene_id})")
        else:
            ligands = ["No gene ID found"]
            logger.warning(f"No PubChem gene ID found for {gene_name}")

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
            'ligands_struct': ligands_struct,
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
            'ligands_struct': [],
        }

def load_from_database(disease_name):
    from app import db
    from db.models import Disease, Gene, DiseaseGene, UniprotProtein, GeneUniprotBridge, Compound, GeneCompoundActivity, UniprotPdb, UniprotInteraction
    
    try:
        disease = Disease.query.filter_by(disease_name=disease_name).first()
        if not disease:
            return None
        
        logger.info(f"Loading cached data for {disease_name} from database")
        
        disease_genes = DiseaseGene.query.filter_by(kegg_disease_id=disease.kegg_disease_id).all()
        
        table_data = []
        for dg in disease_genes:
            gene = Gene.query.filter_by(ncbi_gene_id=dg.ncbi_gene_id).first()
            if not gene:
                continue
            
            bridge = GeneUniprotBridge.query.filter_by(ncbi_gene_id=gene.ncbi_gene_id).first()
            uniprot_id = bridge.uniprot_id if bridge else "N/A"
            
            protein_name = "Protein name not available"
            functional_role = "Functional role not available"
            pdb_ids = []
            receptors = []
            
            if uniprot_id != "N/A":
                protein = UniprotProtein.query.filter_by(uniprot_id=uniprot_id).first()
                if protein:
                    protein_name = protein.protein_name or "Protein name not available"
                    functional_role = protein.functional_role or "Functional role not available"
                
                pdbs = UniprotPdb.query.filter_by(uniprot_id=uniprot_id).all()
                pdb_ids = [p.pdb_id for p in pdbs]
                
                interactions = UniprotInteraction.query.filter_by(uniprot_id=uniprot_id).all()
                receptors = [i.interaction_type for i in interactions]
            
            activities = GeneCompoundActivity.query.filter_by(ncbi_gene_id=gene.ncbi_gene_id).all()
            ligands = []
            ligands_struct = []
            
            for activity in activities:
                compound = Compound.query.filter_by(CID=activity.cid).first()
                if compound:
                    compound_name = compound.preferred_name
                    potency = activity.Ki_concentration
                    if potency:
                        ligands.append(f"{compound_name} ({potency} uM)")
                        ligands_struct.append({"cid": activity.cid, "name": compound_name, "potency_um": float(potency)})
            
            result = {
                'Gene Name': gene.gene_symbol,
                'Gene ID': gene.ncbi_gene_id,
                'UniProt ID': uniprot_id,
                'Protein Name': protein_name,
                'PDB ID': ', '.join(pdb_ids) if pdb_ids else "No PDB IDs",
                'Receptors (Interacting)': ', '.join(receptors) if receptors else "No receptor interaction",
                'Functional Role': functional_role,
                'Ligands': '; '.join(ligands) if ligands else "No ligand data available",
                'ligands_struct': ligands_struct,
                'kegg_gene_id': gene.kegg_gene_id
            }
            table_data.append(result)
        
        logger.info(f"Loaded {len(table_data)} genes from database cache")
        return table_data
        
    except Exception as e:
        logger.error(f"Error loading from database: {e}")
        return None

def save_to_database(disease_name, kegg_disease_id, gene_results):
    from app import db
    from db.models import (
        Disease, Gene, DiseaseGene, UniprotProtein,
        GeneUniprotBridge, Compound, GeneCompoundActivity,
        UniprotPdb, UniprotInteraction
    )
    
    try:
        disease = Disease.query.filter_by(kegg_disease_id=kegg_disease_id).first()
        if not disease:
            disease = Disease(kegg_disease_id=kegg_disease_id, disease_name=disease_name)
            db.session.add(disease)
            db.session.flush()
        
        for gene_data in gene_results:
            gene_id = str(gene_data.get('Gene ID', ''))
            if not gene_id or gene_id == 'N/A':
                continue
            
            gene = Gene.query.filter_by(ncbi_gene_id=gene_id).first()
            if not gene:
                gene = Gene(
                    ncbi_gene_id=gene_id,
                    gene_symbol=gene_data.get('Gene Name', ''),
                    kegg_gene_id=gene_data.get('kegg_gene_id', '') if gene_data.get('kegg_gene_id') else None
                )
                db.session.add(gene)
                db.session.flush()
            
            dg = DiseaseGene.query.filter_by(
                kegg_disease_id=kegg_disease_id,
                ncbi_gene_id=gene_id
            ).first()
            if not dg:
                dg = DiseaseGene(
                    kegg_disease_id=kegg_disease_id,
                    ncbi_gene_id=gene_id
                )
                db.session.add(dg)
            
            uniprot_id = gene_data.get('UniProt ID', '')
            if uniprot_id and uniprot_id != 'N/A':
                protein = UniprotProtein.query.filter_by(uniprot_id=uniprot_id).first()
                if not protein:
                    protein_name = gene_data.get('Protein Name', '')
                    functional_role = gene_data.get('Functional Role', '')
                    
                    protein = UniprotProtein(
                        uniprot_id=uniprot_id,
                        protein_name=protein_name if protein_name else None,
                        functional_role=functional_role if functional_role else None
                    )
                    db.session.add(protein)
                    db.session.flush()
                
                bridge = GeneUniprotBridge.query.filter_by(
                    ncbi_gene_id=gene_id,
                    uniprot_id=uniprot_id
                ).first()
                if not bridge:
                    bridge = GeneUniprotBridge(
                        ncbi_gene_id=gene_id,
                        uniprot_id=uniprot_id
                    )
                    db.session.add(bridge)
                
                pdb_ids = gene_data.get('PDB ID', '')
                if pdb_ids and pdb_ids not in ['N/A', 'No PDB IDs']:
                    for pdb_id in pdb_ids.split(', ')[:3]:
                        pdb_id = pdb_id.strip()
                        if pdb_id:
                            existing_pdb = UniprotPdb.query.filter_by(
                                uniprot_id=uniprot_id,
                                pdb_id=pdb_id
                            ).first()
                            if not existing_pdb:
                                pdb_entry = UniprotPdb(
                                    uniprot_id=uniprot_id,
                                    pdb_id=pdb_id
                                )
                                db.session.add(pdb_entry)
                
                receptors = gene_data.get('Receptors (Interacting)', '')
                if receptors and receptors not in ['N/A', 'No receptor interaction']:
                    for receptor in receptors.split(', ')[:5]:
                        receptor = receptor.strip()
                        if receptor:
                            existing_interaction = UniprotInteraction.query.filter_by(
                                uniprot_id=uniprot_id,
                                interaction_type=receptor
                            ).first()
                            if not existing_interaction:
                                interaction = UniprotInteraction(
                                    uniprot_id=uniprot_id,
                                    interaction_type=receptor
                                )
                                db.session.add(interaction)
            
            ligands_struct = gene_data.get('ligands_struct', [])
            for idx, ligand in enumerate(ligands_struct[:10]):
                cid = str(ligand.get('cid', ''))
                name = ligand.get('name', '')
                potency = str(ligand.get('potency_um', ''))
                
                if not cid:
                    continue
                
                compound = Compound.query.filter_by(CID=cid).first()
                if not compound:
                    compound = Compound(CID=cid, preferred_name=name)
                    db.session.add(compound)
                    db.session.flush()
                
                activity_id = f"{gene_id}_{cid[:20]}_{idx}"
                existing_activity = GeneCompoundActivity.query.filter_by(
                    activity_id=activity_id
                ).first()
                if not existing_activity:
                    activity = GeneCompoundActivity(
                        activity_id=activity_id,
                        ncbi_gene_id=gene_id,
                        cid=cid,
                        Ki_concentration=potency if potency else None
                    )
                    db.session.add(activity)
        
        db.session.commit()
        logger.info(f"Successfully saved data for {disease_name} to database")
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving to database: {e}")
        import traceback
        traceback.print_exc()
        return False

def build_gene_receptor_ligand_table(disease_name, progress_callback=None):
    logger.info(f"Building table for disease: {disease_name}")
    
    cached_data = load_from_database(disease_name)
    if cached_data:
        logger.info(f"Returning {len(cached_data)} cached results for {disease_name}")
        return cached_data

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

    genes = []
    seen_symbols = set()
    for pathway in kegg_data:
        for g in pathway["genes"]:
            symbol = g["name"].split(",")[0].strip()
            if symbol not in seen_symbols:
                seen_symbols.add(symbol)
                genes.append({
                    "symbol": symbol,
                    "kegg_gene_id": g.get("kegg_gene_id")
                })

    total_before_dedup = sum(len(pathway["genes"]) for pathway in kegg_data)
    logger.info(
        f"Found {total_before_dedup} gene entries across pathways, "
        f"deduplicated to {len(genes)} unique gene symbols"
    )

    table_data = []
    total_genes = len(genes)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_gene = {executor.submit(process_gene, g["symbol"]): g for g in genes}

        for i, future in enumerate(concurrent.futures.as_completed(future_to_gene)):
            g = future_to_gene[future]
            try:
                result = future.result()
                result["kegg_gene_id"] = g.get("kegg_gene_id")
                table_data.append(result)

                if progress_callback:
                    progress_callback(i + 1, total_genes, g["symbol"])

            except Exception as e:
                logger.error(f"Exception for gene {g.get('symbol')}: {e}")

    logger.info(f"Completed processing {len(table_data)} genes")
    save_to_database(disease_name, disease_id, table_data)
    return table_data


def query_kegg(disease_name):
    disease_id = retrieve_kegg_disease_id(disease_name)
    if disease_id:
        pathways = retrieve_kegg_pathway_by_disease_id(disease_id)
        if pathways:
            pathway_details = retrieve_kegg_pathway_details(pathways)
            return pathway_details
    return None

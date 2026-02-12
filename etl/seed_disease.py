import os
import sys
from datetime import datetime

# allow imports from project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from db import db
from db.models import (
    Disease, Pathway, DiseasePathway,
    Gene, DiseaseGene,
    UniprotProtein, GeneUniprotBridge,
    UniprotPdb, UniprotInteraction,
    Compound, GeneCompoundActivity
)

from backend import (
    retrieve_kegg_disease_id,
    retrieve_kegg_pathway_by_disease_id,
    retrieve_kegg_pathway_details,
    build_gene_receptor_ligand_table,
)

from flask import Flask


def make_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://diseasenet_user:diseasenet_pass@127.0.0.1:3307/diseasenet"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def truncate(s, n):
    if s is None:
        return None
    s = str(s)
    return s[:n]


def upsert(model, pk_dict, defaults_dict=None):
    """Tiny helper: fetch by PK, create if missing, update if defaults_dict provided."""
    obj = db.session.get(model, tuple(pk_dict.values())) if len(pk_dict) == 1 else None
    if obj is None:
        # fallback for composite PK tables
        obj = model.query.filter_by(**pk_dict).first()

    if obj is None:
        obj = model(**pk_dict)
        if defaults_dict:
            for k, v in defaults_dict.items():
                setattr(obj, k, v)
        db.session.add(obj)
        return obj, True

    if defaults_dict:
        for k, v in defaults_dict.items():
            # only update if new value is not None and current is None/empty
            if v is not None and (getattr(obj, k, None) in (None, "", "N/A")):
                setattr(obj, k, v)

    return obj, False


def seed_disease(disease_name: str):
    app = make_app()

    with app.app_context():
        db.create_all()

        # 1) KEGG disease id
        kegg_disease_id = retrieve_kegg_disease_id(disease_name)
        if not kegg_disease_id:
            raise RuntimeError(f"Could not find KEGG disease id for '{disease_name}'")

        # 2) Disease row
        disease_obj, created = upsert(
            Disease,
            {"kegg_disease_id": kegg_disease_id},
            {"disease_name": truncate(disease_name, 45)}
        )

        # 3) Pathways + Disease_Pathway
        pathways = retrieve_kegg_pathway_by_disease_id(kegg_disease_id) or []
        pathway_ids = [p["pathway_id"] for p in pathways if p.get("pathway_id")]

        if pathway_ids:
            # details includes genes list; may not include pathway_name
            details = retrieve_kegg_pathway_details([{"pathway_id": pid} for pid in pathway_ids]) or []
            for d in details:
                pid = d.get("pathway_id")
                if not pid:
                    continue

                # Try to infer organism_code from id (e.g., "path:hsa05224" or "hsa05224")
                organism_code = None
                if "hsa" in pid:
                    organism_code = "hsa"

                upsert(Pathway, {"kegg_pathway_id": truncate(pid, 45)}, {"organism_code": truncate(organism_code, 45)})

                upsert(DiseasePathway, {
                    "kegg_disease_id": kegg_disease_id,
                    "kegg_pathway_id": truncate(pid, 45)
                })

        db.session.commit()

        # 4) Gene table + disease_gene + uniprot tables + compound activity
        # This gives you per-gene rows (requires the backend changes described above)
        rows = build_gene_receptor_ligand_table(disease_name) or []

        for row in rows:
            gene_symbol = truncate(row.get("Gene Name"), 45)
            ncbi_gene_id = row.get("Gene ID")
            if not ncbi_gene_id or ncbi_gene_id in ("N/A", "Error", "No gene ID found"):
                # ERD requires ncbi_gene_id PK; skip genes without a usable ID
                continue
            ncbi_gene_id = truncate(ncbi_gene_id, 45)

            kegg_gene_id = row.get("kegg_gene_id")
            kegg_gene_id = truncate(kegg_gene_id, 45) if kegg_gene_id else None

            # Gene
            upsert(Gene, {"ncbi_gene_id": ncbi_gene_id}, {
                "gene_symbol": gene_symbol,
                "kegg_gene_id": kegg_gene_id
            })

            # Disease_gene bridge
            upsert(DiseaseGene, {
                "kegg_disease_id": kegg_disease_id,
                "ncbi_gene_id": ncbi_gene_id
            })

            # UniProt protein + bridge
            uniprot_id = row.get("UniProt ID")
            if uniprot_id and uniprot_id not in ("N/A", "Error"):
                uniprot_id = truncate(uniprot_id, 45)

                protein_name = truncate(row.get("Protein Name"), 45)
                functional_role = truncate(row.get("Functional Role"), 45)  # ERD exact (VARCHAR(45))

                upsert(UniprotProtein, {"uniprot_id": uniprot_id}, {
                    "protein_name": protein_name,
                    "functional_role": functional_role
                })

                upsert(GeneUniprotBridge, {
                    "ncbi_gene_id": ncbi_gene_id,
                    "uniprot_id": uniprot_id
                })

                # PDB IDs → uniprot_pdb
                pdb_str = row.get("PDB ID") or ""
                pdbs = [p.strip() for p in pdb_str.split(",") if p.strip() and p.strip() != "No PDB IDs"]
                for pdb_id in pdbs:
                    upsert(UniprotPdb, {"uniprot_id": uniprot_id, "pdb_id": truncate(pdb_id, 45)})

                # UniProt interactions
                # Your current backend returns receptor-like names as a comma-separated string.
                # Your ERD uses "interaction_type" (string). We'll store each interactor name as interaction_type.
                inter_str = row.get("Receptors (Interacting)") or ""
                if inter_str and "No receptor" not in inter_str and inter_str != "Error":
                    interactors = [x.strip() for x in inter_str.split(",") if x.strip()]
                    for it in interactors:
                        _attach = truncate(it, 45)
                        upsert(UniprotInteraction, {"uniprot_id": uniprot_id, "interaction_type": _attach})

            # Compounds + activity
            ligands_struct = row.get("ligands_struct") or []
            for lig in ligands_struct:
                cid = lig.get("cid")
                if not cid:
                    continue
                cid = truncate(str(cid), 45)

                preferred_name = truncate(lig.get("name"), 45)
                upsert(Compound, {"CID": cid}, {"preferred_name": preferred_name})

                potency = lig.get("potency_um")
                ki_str = truncate(str(potency) if potency is not None else None, 45)

                # activity_id required by ERD — make it deterministic, <=45 chars
                activity_id = truncate(f"{ncbi_gene_id}_{cid}", 45)

                upsert(GeneCompoundActivity, {"activity_id": activity_id}, {
                    "ncbi_gene_id": ncbi_gene_id,
                    "cid": cid,
                    "Ki_concentration": ki_str
                })

        db.session.commit()
        print(f"Seeded ERD for '{disease_name}' (KEGG: {kegg_disease_id}) with {len(rows)} gene rows.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python etl/seed_disease.py \"Breast cancer\"")
        sys.exit(1)
    seed_disease(sys.argv[1])

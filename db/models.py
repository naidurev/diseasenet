from . import db


class Disease(db.Model):
    __tablename__ = "Disease"

    kegg_disease_id = db.Column(db.String(50), primary_key=True)
    disease_name = db.Column(db.String(45), nullable=False)

    __table_args__ = (
        db.Index("idx_disease_name", "disease_name"),
    )


class Pathway(db.Model):
    __tablename__ = "Pathway"

    kegg_pathway_id = db.Column(db.String(45), primary_key=True)
    pathway_name = db.Column(db.String(45), nullable=True)
    organism_code = db.Column(db.String(45), nullable=True)

    __table_args__ = (
        db.Index("idx_pathway_org", "organism_code"),
    )


class DiseasePathway(db.Model):
    __tablename__ = "Disease_Pathway"

    kegg_disease_id = db.Column(db.String(50), db.ForeignKey("Disease.kegg_disease_id"), primary_key=True)
    kegg_pathway_id = db.Column(db.String(45), db.ForeignKey("Pathway.kegg_pathway_id"), primary_key=True)


class Gene(db.Model):
    __tablename__ = "Gene"

    # ERD shows ncbi_gene_id is the PK (you’re currently getting this via PubChem GeneID)
    ncbi_gene_id = db.Column(db.String(45), primary_key=True)

    gene_symbol = db.Column(db.String(45), nullable=False)
    kegg_gene_id = db.Column(db.String(45), nullable=True)  # e.g., "hsa:2099"

    __table_args__ = (
        db.Index("idx_gene_symbol", "gene_symbol"),
        db.Index("idx_gene_kegg", "kegg_gene_id"),
    )


class DiseaseGene(db.Model):
    __tablename__ = "Disease_gene"

    kegg_disease_id = db.Column(db.String(50), db.ForeignKey("Disease.kegg_disease_id"), primary_key=True)
    ncbi_gene_id = db.Column(db.String(45), db.ForeignKey("Gene.ncbi_gene_id"), primary_key=True)


class UniprotProtein(db.Model):
    __tablename__ = "uniprot_protein"

    uniprot_id = db.Column(db.String(45), primary_key=True)
    protein_name = db.Column(db.String(45), nullable=True)
    functional_role = db.Column(db.String(45), nullable=True)  # ERD shows VARCHAR(45); your data may be longer

    # If your UniProt function text is long, change functional_role to db.Text in both schema+ETL.
    # But to be "exact ERD", we keep VARCHAR(45). (You may want to expand later.)


class GeneUniprotBridge(db.Model):
    __tablename__ = "Gene_uniprot_bridge"

    ncbi_gene_id = db.Column(db.String(45), db.ForeignKey("Gene.ncbi_gene_id"), primary_key=True)
    uniprot_id = db.Column(db.String(45), db.ForeignKey("uniprot_protein.uniprot_id"), primary_key=True)


class UniprotPdb(db.Model):
    __tablename__ = "uniprot_pdb"

    uniprot_id = db.Column(db.String(45), db.ForeignKey("uniprot_protein.uniprot_id"), primary_key=True)
    pdb_id = db.Column(db.String(45), primary_key=True)


class UniprotInteraction(db.Model):
    __tablename__ = "Uniprot_interaction"

    uniprot_id = db.Column(db.String(45), db.ForeignKey("uniprot_protein.uniprot_id"), primary_key=True)
    interaction_type = db.Column(db.String(45), primary_key=True)


class Compound(db.Model):
    __tablename__ = "Compound"

    CID = db.Column(db.String(45), primary_key=True)
    preferred_name = db.Column(db.String(45), nullable=True)


class GeneCompoundActivity(db.Model):
    __tablename__ = "Gene_compound_activity"

    activity_id = db.Column(db.String(45), primary_key=True)
    ncbi_gene_id = db.Column(db.String(45), db.ForeignKey("Gene.ncbi_gene_id"), nullable=False)
    cid = db.Column(db.String(45), db.ForeignKey("Compound.CID"), nullable=False)
    Ki_concentration = db.Column(db.String(45), nullable=True)  # ERD says VARCHAR; you’ll store potency as string

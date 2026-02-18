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

    ncbi_gene_id = db.Column(db.String(45), primary_key=True)
    gene_symbol = db.Column(db.String(45), nullable=False)
    kegg_gene_id = db.Column(db.String(45), nullable=True)

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
    protein_name = db.Column(db.Text, nullable=True)
    functional_role = db.Column(db.Text, nullable=True)


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
    interaction_type = db.Column(db.Text, primary_key=True)


class Compound(db.Model):
    __tablename__ = "Compound"

    CID = db.Column(db.String(45), primary_key=True)
    preferred_name = db.Column(db.Text, nullable=True)


class GeneCompoundActivity(db.Model):
    __tablename__ = "Gene_compound_activity"

    activity_id = db.Column(db.String(45), primary_key=True)
    ncbi_gene_id = db.Column(db.String(45), db.ForeignKey("Gene.ncbi_gene_id"), nullable=False)
    cid = db.Column(db.String(45), db.ForeignKey("Compound.CID"), nullable=False)
    Ki_concentration = db.Column(db.Text, nullable=True)


class UserSearch(db.Model):
    __tablename__ = "user_search"
    
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), nullable=False)
    disease_name = db.Column(db.String(200), nullable=False)
    searched_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    __table_args__ = (
        db.Index("idx_user_email", "user_email"),
        db.Index("idx_searched_at", "searched_at"),
    )


class User(db.Model):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    __table_args__ = (
        db.Index("idx_username", "username"),
    )

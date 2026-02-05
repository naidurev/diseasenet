# 🧬 DiseaseNet

A comprehensive disease-gene-protein-ligand database search tool that integrates data from KEGG, UniProt, and PubChem databases.

![DiseaseNet Screenshot](https://img.shields.io/badge/Status-Production%20Ready-success)
![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)

---

## 🎯 Overview

DiseaseNet is a Flask web application that allows researchers to quickly search for disease-associated genes and retrieve comprehensive information including:

- Gene and protein information
- Receptor interactions
- Active ligands with bioactivity data
- 3D protein structures (PDB IDs)
- Functional roles and pathways

---

## ✨ Features

- **🔍 Intelligent Search**: Autocomplete and fuzzy matching for disease names
- **📊 Comprehensive Data**: Integration of KEGG, UniProt, and PubChem databases
- **⚡ Real-time Progress**: Live updates during data processing
- **📋 Interactive Results**: Sortable, filterable table with 100+ genes per disease
- **📥 Export Options**: Download results as CSV
- **💡 Smart UI**: Copy cells with one click, highlight on copy
- **🎨 Modern Design**: Clean interface with responsive layout

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/diseasenet.git
cd diseasenet
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the application**
```bash
python app.py
```

4. **Open in browser**
```
http://127.0.0.1:5000/
```

---

## 📖 Usage

1. **Enter a disease name** (e.g., "Breast cancer", "Diabetes mellitus")
2. **Select from autocomplete suggestions** or use example buttons
3. **Wait for processing** (30-60 seconds for ~100 genes)
4. **Explore results**:
   - Sort by clicking column headers
   - Filter using the search box
   - Copy individual cells by hovering and clicking "Copy"
5. **Export data** by clicking "Export CSV"

---

## 🗂️ Project Structure

```
diseasenet/
├── app.py                  # Flask application & routes
├── backend.py              # API integration & data processing
├── templates/
│   └── index.html          # Frontend interface
├── static/
│   └── images/
│       └── image.png       # Background image
├── requirements.txt        # Python dependencies
├── README.md              # This file
└── .gitignore            # Git ignore rules
```

---

## 🔬 Data Sources

### KEGG (Kyoto Encyclopedia of Genes and Genomes)
- Disease-pathway associations
- Gene identification
- Biological pathway context

### UniProt (Universal Protein Resource)
- Protein names and descriptions
- Functional annotations
- PDB structure IDs
- Receptor interactions

### PubChem (NCBI Chemical Database)
- Bioactivity screening data
- Active compound identification
- Ligand potency values (μM)

---

## 📊 Output Data

Each search returns a comprehensive table with:

| Column | Description |
|--------|-------------|
| **Gene Name** | Official gene symbol |
| **Gene ID** | NCBI Gene ID |
| **UniProt ID** | Protein database identifier |
| **Protein Name** | Full protein name |
| **Receptors** | Interacting receptor proteins |
| **Functional Role** | Biological function description |
| **PDB ID** | 3D structure database IDs |
| **Ligands** | Active compounds with potency |

---

## 🛠️ Technical Details

### Built With

- **Backend**: Flask (Python)
- **APIs**: KEGG REST, UniProt REST, PubChem PUG REST
- **Data Processing**: Pandas, NumPy
- **Fuzzy Matching**: FuzzyWuzzy
- **Frontend**: HTML5, CSS3, Vanilla JavaScript

### Performance

- Parallel processing with 5 concurrent workers
- Rate limiting: 4 requests/second to PubChem
- Retry logic with exponential backoff
- Expected processing time: ~1-2 seconds per gene

### Features Implemented

✅ Disease search with fuzzy matching  
✅ Real-time autocomplete  
✅ Animated progress bar  
✅ Sortable & filterable results table  
✅ One-click cell copying with visual feedback  
✅ CSV export  
✅ Recent searches history  
✅ Example disease quick access  
✅ Responsive design  
✅ Error handling & retry logic  

---

## 🖼️ Screenshots

### Home Page
Clean search interface with autocomplete and recent searches.

### Results Page
Interactive table with sortable columns and copy functionality.

### Progress Tracking
Real-time updates during data processing.

---

## 📝 Example Searches

Try these diseases to see DiseaseNet in action:

- **Breast cancer** (~104 genes)
- **Diabetes mellitus** (~87 genes)
- **Alzheimer disease** (~93 genes)
- **Atopic dermatitis** (~45 genes)

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- **KEGG** for disease and pathway data
- **UniProt** for comprehensive protein information
- **PubChem** for chemical bioactivity data
- Developed as part of MSc Bioinformatics for Health Sciences at UPF

---

## 📧 Contact

**Author**: Austin Gilbride, Brigita Medelyte, Revanth Naidu  
**Institution**: Universitat Pompeu Fabra (UPF)  
**Program**: MSc Bioinformatics for Health Sciences  
**Year**: 2024-2025

---

## 🔮 Future Enhancements

- [ ] 3D protein structure viewer integration
- [ ] Disease comparison tool
- [ ] Database caching for faster results
- [ ] User authentication and saved searches
- [ ] PDF report generation
- [ ] Network visualization of gene interactions
- [ ] Drug information integration
- [ ] Batch gene lookup

---

**⭐ If you find this project useful, please consider giving it a star!**

---

*Built with ❤️ for the bioinformatics community*

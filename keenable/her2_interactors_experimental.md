# HER2 (ERBB2) interactors with experimental evidence

A filtered version of [`her2_interactors_literature.md`](her2_interactors_literature.md) that keeps only primary research papers with **lab evidence** linking each gene to HER2.

- **Kept:** either **physical** evidence (the protein binds HER2 or forms a complex with it, e.g. co-immunoprecipitation, pull-down, crosslinking, PDZ or SH2 binding) or **functional** evidence (knockdown, knockout, a mutant or an inhibitor changes HER2 signaling, HER2-driven growth or anti-HER2 drug response).
- **Removed:** reviews and an editorial (8 papers, listed at the end). 21 of the original 29 papers stayed.
- **Added:** 5 experimental papers found with Keenable for genes that had only review support (EGFR, ERBB3, ERBB4, ESR1, PGR).
- **Checked:** every paper's PubMed abstract and article type (2026-11-14). The "Experiment" column paraphrases the abstract. Full methods were not read.

**Result:** 26 experimental papers (21 kept + 5 added). Every candidate gene in the original list has at least one.

## Papers

| Gene(s) | Evidence | Experiment (from the abstract) | Model | PMID | Year | Title |
|---|---|---|---|---|---|---|
| `EGFR` | Physical + functional | EGF-receptor co-immunoprecipitates with HER2 after crosslinking; EGF triggers heterodimers and boosts HER2 phosphorylation | SKBR3 breast cancer cells | [1980216](https://pubmed.ncbi.nlm.nih.gov/1980216/) ★ | 1990 | Heterodimerization of the erbB-1 and erbB-2 receptors in human breast carcinoma cells: a mechanism for receptor transregulation |
| `ERBB3` | Functional | Removing ERBB3 stops proliferation of HER2-overexpressing cells, like losing HER2; ERBB3 couples HER2 to PI3K/AKT | HER2+ breast cancer cells | [12853564](https://pubmed.ncbi.nlm.nih.gov/12853564/) ★ | 2003 | The ErbB2/ErbB3 heterodimer functions as an oncogenic unit: ErbB2 requires ErbB3 to drive breast tumor cell proliferation |
| `ERBB3`, `IGF1R` | Physical + functional | HER2, HER3 and IGF-1R form a three-receptor complex; shRNA against HER3 or IGF-1R restores trastuzumab sensitivity | Trastuzumab-resistant breast cancer cells | [20103628](https://pubmed.ncbi.nlm.nih.gov/20103628/) | 2010 | Heterotrimerization of the growth factor receptors erbB2, erbB3, and insulin-like growth factor-i receptor in breast cancer cells resistant to herceptin |
| `ERBB4` | Functional | Trastuzumab drives HER4 cleavage and nuclear entry; siRNA against HER4 reverses resistance; nuclear HER4 predicts poor response in patients | HER2+ breast cancer cells, BT474 xenografts, patient tumors | [25153719](https://pubmed.ncbi.nlm.nih.gov/25153719/) ★ | 2014 | Nuclear HER4 mediates acquired resistance to trastuzumab and is associated with poor outcome in HER2 positive breast cancer |
| `IGF1R` | Physical + functional | IGF-1R binds HER2 only in resistant cells; IGF-1 raises HER2 phosphorylation; breaking the dimer restores trastuzumab response | SKBR3-derived trastuzumab-resistant cells | [16322262](https://pubmed.ncbi.nlm.nih.gov/16322262/) | 2005 | Insulin-like growth factor-I receptor/human epidermal growth factor receptor 2 heterodimerization contributes to trastuzumab resistance of breast cancer cells |
| `HSP90AA1` | Physical + functional | HSP90 binds a specific loop in the HER2 kinase domain and limits HER2 heterodimer formation | Cell lines | [15568014](https://pubmed.ncbi.nlm.nih.gov/15568014/) | 2004 | Hsp90 restrains ErbB-2/HER2 signalling by limiting heterodimer formation |
| `HSP90AA1`, `ERBB3` | Physical + functional | Cell-surface HSP90 binds the HER2 extracellular domain (GST pull-down); a blocking antibody reduces HER2/HER3 activation and invasion | Breast cancer cells | [18056992](https://pubmed.ncbi.nlm.nih.gov/18056992/) | 2007 | A critical role for HSP90 in cancer cell invasion involves interaction with the extracellular domain of HER-2 |
| `HSP90AA1` | Physical + functional | Full-length HER2 and p95-HER2 bind HSP90; HSP90 inhibitors degrade both and stop tumor growth | p95-HER2 tumor models in vitro and in vivo | [19855434](https://pubmed.ncbi.nlm.nih.gov/19855434/) | 2009 | Inhibitors of HSP90 block p95-HER2 signaling in Trastuzumab-resistant tumors and suppress their growth |
| `STUB1` | Functional | Knockdown and overexpression show CHIP sends newly made HER2 to proteasomal degradation | HER2+ breast cancer cells | [34439093](https://pubmed.ncbi.nlm.nih.gov/34439093/) | 2021 | CHIP/STUB1 Ubiquitin Ligase Functions as a Negative Regulator of ErbB2 by Promoting Its Early Post-Biosynthesis Degradation |
| `ATM` | Physical + functional | ATM promotes the HER2-HSP90 complex and prevents HER2 ubiquitination; ATM supports HER2 tumor growth in vitro and in vivo | HER2+ breast cancer cells and tumors | [25881002](https://pubmed.ncbi.nlm.nih.gov/25881002/) | 2015 | ATM kinase sustains HER2 tumorigenicity in breast cancer |
| `GRB7`, `SHC1` | Physical | GRB7 binds phosphorylated HER2 through its SH2 domain; much of phospho-HER2 in SKBR3 cells is bound to GRB7; GRB7 is co-amplified with HER2 | SKBR3 cells, breast tumors | [7907978](https://pubmed.ncbi.nlm.nih.gov/7907978/) | 1994 | The SH2 domain protein GRB-7 is co-amplified, overexpressed and in a tight complex with HER2 in breast cancer |
| `GRB7`, `SHC1`, `VAV2` | Physical + functional | Co-IP shows GRB7 brings SHC into the HER2 complex; GRB7 siRNA lowers RAS activation, proliferation and migration | HER2+ and trastuzumab-resistant breast cancer cells | [23593540](https://pubmed.ncbi.nlm.nih.gov/23593540/) | 2013 | Dissecting GRB7-mediated signals for proliferation and migration in HER2 overexpressing breast tumor cells: GTP-ase rules |
| `STARD3`, `GRB7`, `PSMD3`, `PGAP3` | Functional (genetic) | Co-silencing these co-amplified 17q12 genes together with HER2 adds to the loss of cell viability | HER2+ breast cancer cells, 71 tumors (aCGH) | [23253899](https://pubmed.ncbi.nlm.nih.gov/23253899/) | 2012 | The HER2 amplicon includes several genes required for the growth and survival of HER2 positive breast cancer cells |
| `MUC4`, `TNF` | Functional | TNF-alpha induces MUC4, which reduces trastuzumab binding to HER2; MUC4 siRNA restores binding and response | HER2+ breast cancer cells, tumors, 78-patient cohort | [27698002](https://pubmed.ncbi.nlm.nih.gov/27698002/) | 2016 | TNFα-Induced Mucin 4 Expression Elicits Trastuzumab Resistance in HER2-Positive Breast Cancer |
| `MUC4` | Functional | Lowering MUC4 with N-acetylcysteine improves HER2 access (immunoPET) and trastuzumab response in MUC4+ tumors | JIMT1 / SKBR3 xenografts | [28915583](https://pubmed.ncbi.nlm.nih.gov/28915583/) | 2017 | N-Acetylcysteine breaks resistance to trastuzumab caused by MUC4 overexpression in human HER2 positive BC-bearing nude mice |
| `CDCP1`, `SRC` | Physical + functional | CDCP1 binds HER2 through its intracellular domain, increases HER2-SRC binding and HER2 signaling, and drives tumor formation | Breast cancer cell lines, in vivo tumors | [25892239](https://pubmed.ncbi.nlm.nih.gov/25892239/) | 2015 | Interaction of CDCP1 with HER2 enhances HER2-driven tumorigenesis and promotes trastuzumab resistance in breast cancer |
| `SRC`, `PTEN` | Functional | SRC is activated in trastuzumab-resistant cells; blocking SRC with trastuzumab removes resistant tumors in vivo | HER2+ breast cancer cells, xenografts, patients | [21399647](https://pubmed.ncbi.nlm.nih.gov/21399647/) | 2011 | Combating trastuzumab resistance by targeting SRC, a common node downstream of multiple resistance pathways |
| `PTEN`, `SRC` | Functional | Trastuzumab activates PTEN by inhibiting SRC; lowering PTEN causes resistance in vitro and in vivo | HER2+ breast cancer cells, mice, patients | [15324695](https://pubmed.ncbi.nlm.nih.gov/15324695/) | 2004 | PTEN activation contributes to tumor inhibition by trastuzumab, and loss of PTEN predicts trastuzumab resistance in patients |
| `PIK3CA` | Functional (genetic) | Mice expressing HER2 plus mutant PIK3CA (H1047R) get tumors sooner and resist anti-HER2 drug combinations | Transgenic mouse mammary tumors | [23940356](https://pubmed.ncbi.nlm.nih.gov/23940356/) | 2013 | Mutant PIK3CA accelerates HER2-driven transgenic mammary tumors and induces resistance to combinations of anti-HER2 therapies |
| `PTPN1` | Functional (genetic) | Ptpn1 knockout or a PTP1B inhibitor delays HER2-driven mammary tumors and lung metastasis | NDL2 HER2 transgenic mice | [17259984](https://pubmed.ncbi.nlm.nih.gov/17259984/) | 2007 | Protein tyrosine phosphatase 1B deficiency or inhibition delays ErbB2-induced mammary tumorigenesis and protects from lung metastasis |
| `ITGB4`, `STAT3`, `JUN` | Physical + functional | Beta-4 integrin forms a complex with HER2; deleting its signaling domain slows HER2 tumors and blunts STAT3 and c-Jun activation | HER2 transgenic mice, primary cells | [16901783](https://pubmed.ncbi.nlm.nih.gov/16901783/) | 2006 | Beta 4 integrin amplifies ErbB2 signaling to promote mammary tumorigenesis |
| `MEMO1`, `SHC1` | Physical + functional | MEMO1 binds a phospho-Y1227 HER2 peptide, likely through SHC; MEMO-defective cells cannot migrate in response to HER2 | Breast carcinoma cells | [15156151](https://pubmed.ncbi.nlm.nih.gov/15156151/) | 2004 | Memo mediates ErbB2-driven cell motility |
| `ERBIN` | Physical + functional | ERBIN's PDZ domain binds HER2 directly; mutating the binding site mislocalizes HER2 | Epithelial cell lines | [10878805](https://pubmed.ncbi.nlm.nih.gov/10878805/) | 2000 | ERBIN: a basolateral PDZ protein that interacts with the mammalian ERBB2/HER2 receptor |
| `ERBIN`, `SLC9A3R1`, `EZR`, `HSP90AA1` | Physical + functional | Erbin binds NHERF1, Ezrin and HER2; Erbin knockdown breaks up the HER2/NHERF1/Ezrin/HSP90 complex and lowers HER2 signaling | SKBR3 cells, MMTV-Neu mice, human DCIS | [40390040](https://pubmed.ncbi.nlm.nih.gov/40390040/) | 2025 | Erbin interacts with NHERF1 and Ezrin to stabilize a membrane ErbB2 signaling complex in HER2-positive breast cancer |
| `ESR1`, `EGFR`, `NCOA3` | Functional | In HER2-overexpressing MCF-7 cells, ER and EGFR/HER2 phosphorylate and activate each other and tamoxifen acts as an agonist; gefitinib blocks this | MCF-7/HER2-18 cells and xenografts | [15199112](https://pubmed.ncbi.nlm.nih.gov/15199112/) ★ | 2004 | Mechanisms of tamoxifen resistance: increased estrogen receptor-HER2/neu cross-talk in ER/HER2-positive breast cancer |
| `PGR`, `STAT3` | Physical + functional | Progestin-activated PR moves HER2 into the nucleus, where HER2 joins STAT3 (and PR) on the cyclin D1 promoter to drive growth | Breast cancer cells, mouse mammary tumors | [20876300](https://pubmed.ncbi.nlm.nih.gov/20876300/) ★ | 2010 | Progesterone receptor induces ErbB-2 nuclear translocation to promote breast cancer growth via a novel transcriptional effect: ErbB-2 function as a coactivator of Stat3 |

★ = new paper found with Keenable for this filter (not in the original list).

## Strongest evidence per gene

| Evidence | Genes |
|---|---|
| **Physical binding to HER2 shown** | `EGFR`, `ERBB3`, `IGF1R`, `HSP90AA1`, `ATM` (via HSP90 complex), `GRB7`, `SHC1`, `CDCP1`, `ITGB4`, `MEMO1`, `ERBIN`, `SLC9A3R1`, `EZR`, `PGR` (nuclear complex with STAT3) |
| **Functional only** | `ERBB4`, `STUB1`, `STARD3`, `PSMD3`, `PGAP3`, `MUC4`, `TNF`, `SRC`, `PTEN`, `PIK3CA`, `PTPN1`, `STAT3`, `JUN`, `VAV2`, `ESR1` |

The ESR1 paper also names the ER coactivator `NCOA3` (AIB1), which isn't in the original candidate list.

## Removed (no primary experimental data)

| PMID | Type | Title |
|---|---|---|
| [39020378](https://pubmed.ncbi.nlm.nih.gov/39020378/) | Review | HER3 receptor and its role in the therapeutic management of metastatic breast cancer |
| [30057690](https://pubmed.ncbi.nlm.nih.gov/30057690/) | Review | HER3 signaling and targeted therapy in cancer |
| [39062682](https://pubmed.ncbi.nlm.nih.gov/39062682/) | Review | A Comprehensive Review of HER2 in Cancer Biology and Therapeutics |
| [17274834](https://pubmed.ncbi.nlm.nih.gov/17274834/) | Review | HER2 (ERBB2): functional diversity from structurally conserved building blocks |
| [37258523](https://pubmed.ncbi.nlm.nih.gov/37258523/) | Review | Estrogen/HER2 receptor crosstalk in breast cancer |
| [27800032](https://pubmed.ncbi.nlm.nih.gov/27800032/) | Review | Resistance to therapy in ER positive and HER2 positive breast cancers |
| [39137598](https://pubmed.ncbi.nlm.nih.gov/39137598/) | Review | Advances in HER2-Targeted Therapies |
| [27358378](https://pubmed.ncbi.nlm.nih.gov/27358378/) | Editorial / comment | PIK3CA mutations in HER2-positive breast cancer: an ongoing conundrum |

Research prototype; not for medical decisions.

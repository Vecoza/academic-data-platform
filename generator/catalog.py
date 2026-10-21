"""Static description of the university: faculties, programs and their subject areas.

Mandatory subjects are listed in curriculum order, foundations first. Elective topics are
combined with name patterns to produce elective courses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramSpec:
    name: str
    code: str
    degree_level: str
    mandatory_subjects: tuple[str, ...]
    elective_topics: tuple[str, ...]


@dataclass(frozen=True)
class FacultySpec:
    name: str
    code: str
    programs: tuple[ProgramSpec, ...]


FACULTIES: tuple[FacultySpec, ...] = (
    FacultySpec(
        name="Faculty of Electrical Engineering and Computing",
        code="FEEC",
        programs=(
            ProgramSpec(
                name="Computer Science",
                code="CSB",
                degree_level="bachelor",
                mandatory_subjects=(
                    "Mathematical Analysis",
                    "Programming",
                    "Digital Logic",
                    "Linear Algebra",
                    "Discrete Mathematics",
                    "Data Structures",
                    "Computer Architecture",
                    "Probability and Statistics",
                    "Algorithms",
                    "Operating Systems",
                    "Databases",
                    "Computer Networks",
                ),
                elective_topics=(
                    "Web Development",
                    "Computer Graphics",
                    "Information Security",
                    "Mobile Applications",
                    "Human-Computer Interaction",
                    "Cloud Computing",
                    "Game Development",
                    "Compilers",
                    "Embedded Systems",
                    "Data Visualization",
                    "Functional Programming",
                    "Software Testing",
                ),
            ),
            ProgramSpec(
                name="Computer Science",
                code="CSM",
                degree_level="master",
                mandatory_subjects=(
                    "Advanced Algorithms",
                    "Machine Learning",
                    "Distributed Systems",
                    "Software Architecture",
                    "Formal Methods",
                    "Data Engineering",
                    "Research Methods",
                    "Parallel Computing",
                ),
                elective_topics=(
                    "Deep Learning",
                    "Natural Language Processing",
                    "Computer Vision",
                    "Cryptography",
                    "Reinforcement Learning",
                    "Big Data Systems",
                    "Quantum Computing",
                    "Robotics",
                    "Information Retrieval",
                    "Bioinformatics",
                    "Blockchain Systems",
                    "Recommender Systems",
                ),
            ),
            ProgramSpec(
                name="Electrical Engineering",
                code="EEB",
                degree_level="bachelor",
                mandatory_subjects=(
                    "Mathematical Analysis",
                    "Physics",
                    "Electric Circuits",
                    "Linear Algebra",
                    "Electronics",
                    "Signals and Systems",
                    "Electromagnetics",
                    "Measurement Techniques",
                    "Control Systems",
                    "Power Systems",
                    "Electrical Machines",
                    "Communication Systems",
                ),
                elective_topics=(
                    "Renewable Energy",
                    "Power Electronics",
                    "Microcontrollers",
                    "Antennas and Propagation",
                    "Digital Signal Processing",
                    "Smart Grids",
                    "Electric Vehicles",
                    "Industrial Automation",
                    "Optoelectronics",
                    "High Voltage Engineering",
                    "Sensor Networks",
                    "Audio Engineering",
                ),
            ),
        ),
    ),
    FacultySpec(
        name="Faculty of Economics and Business",
        code="FEB",
        programs=(
            ProgramSpec(
                name="Business Economics",
                code="BEB",
                degree_level="bachelor",
                mandatory_subjects=(
                    "Principles of Economics",
                    "Business Mathematics",
                    "Accounting",
                    "Business Law",
                    "Microeconomics",
                    "Macroeconomics",
                    "Statistics",
                    "Marketing",
                    "Corporate Finance",
                    "Management",
                    "Business Informatics",
                    "International Trade",
                ),
                elective_topics=(
                    "Entrepreneurship",
                    "Digital Marketing",
                    "Tourism Economics",
                    "Human Resource Management",
                    "Supply Chain Management",
                    "Public Finance",
                    "Consumer Behaviour",
                    "Business Ethics",
                    "Project Management",
                    "E-Commerce",
                    "Retail Management",
                    "Negotiation",
                ),
            ),
            ProgramSpec(
                name="Finance",
                code="FIM",
                degree_level="master",
                mandatory_subjects=(
                    "Financial Markets",
                    "Econometrics",
                    "Investment Analysis",
                    "Risk Management",
                    "Financial Reporting",
                    "Monetary Policy",
                    "Corporate Valuation",
                    "Research Methods in Finance",
                ),
                elective_topics=(
                    "Behavioural Finance",
                    "Banking",
                    "Insurance",
                    "Derivatives",
                    "Portfolio Management",
                    "Financial Technology",
                    "Mergers and Acquisitions",
                    "International Finance",
                    "Real Estate Finance",
                    "Sustainable Finance",
                    "Quantitative Trading",
                    "Auditing",
                ),
            ),
        ),
    ),
    FacultySpec(
        name="Faculty of Science",
        code="FSC",
        programs=(
            ProgramSpec(
                name="Mathematics",
                code="MAB",
                degree_level="bachelor",
                mandatory_subjects=(
                    "Mathematical Analysis",
                    "Linear Algebra",
                    "Elementary Mathematics",
                    "Programming",
                    "Discrete Mathematics",
                    "Differential Equations",
                    "Probability",
                    "Algebra",
                    "Numerical Mathematics",
                    "Geometry",
                    "Complex Analysis",
                    "Mathematical Statistics",
                ),
                elective_topics=(
                    "Topology",
                    "Number Theory",
                    "Combinatorics",
                    "Graph Theory",
                    "Optimization",
                    "Game Theory",
                    "Mathematical Logic",
                    "Cryptography",
                    "Financial Mathematics",
                    "Dynamical Systems",
                    "Set Theory",
                    "History of Mathematics",
                ),
            ),
            ProgramSpec(
                name="Physics",
                code="PHB",
                degree_level="bachelor",
                mandatory_subjects=(
                    "General Physics",
                    "Mathematical Analysis",
                    "Linear Algebra",
                    "Physics Laboratory",
                    "Mechanics",
                    "Thermodynamics",
                    "Electromagnetism",
                    "Mathematical Methods of Physics",
                    "Optics",
                    "Quantum Physics",
                    "Statistical Physics",
                    "Solid State Physics",
                ),
                elective_topics=(
                    "Astrophysics",
                    "Nuclear Physics",
                    "Biophysics",
                    "Particle Physics",
                    "Computational Physics",
                    "Geophysics",
                    "Plasma Physics",
                    "Acoustics",
                    "Medical Physics",
                    "Atmospheric Physics",
                    "Relativity",
                    "Nanophysics",
                ),
            ),
        ),
    ),
    FacultySpec(
        name="Faculty of Mechanical Engineering",
        code="FME",
        programs=(
            ProgramSpec(
                name="Mechanical Engineering",
                code="MEB",
                degree_level="bachelor",
                mandatory_subjects=(
                    "Mathematical Analysis",
                    "Engineering Drawing",
                    "Statics",
                    "Physics",
                    "Strength of Materials",
                    "Materials Science",
                    "Dynamics",
                    "Thermodynamics",
                    "Machine Elements",
                    "Fluid Mechanics",
                    "Manufacturing Technology",
                    "Heat Transfer",
                ),
                elective_topics=(
                    "Computer-Aided Design",
                    "Robotics",
                    "Automotive Engineering",
                    "Welding Technology",
                    "Turbomachinery",
                    "Finite Element Method",
                    "Mechatronics",
                    "Additive Manufacturing",
                    "Refrigeration",
                    "Production Planning",
                    "Vibrations",
                    "Hydraulics and Pneumatics",
                ),
            ),
        ),
    ),
)

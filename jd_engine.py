
from __future__ import annotations
import re
from collections import Counter
import pandas as pd
STOP_LINES = {
    "about us",
    "about the company",
    "about the organization",
    "equal opportunity employer",
    "apply now",
    "job description",
    "job overview",
    "role overview",
    "location",
    "compensation",
    "salary",
    "benefits",
}
MANDATORY_WORDS = [
    "must",
    "mandatory",
    "required",
    "requirement",
    "essential",
    "minimum",
    "at least",
    "need to",
    "should have",
    "must have",
    "is required",
    "non-negotiable",
]
PREFERRED_WORDS = [
    "preferred",
    "preferably",
    "good to have",
    "nice to have",
    "bonus",
    "advantage",
    "desirable",
    "plus",
]
CATEGORY_PATTERNS = {

    "Technical skills and tools": [
        "python", "java", "sql", "excel", "power bi",
        "tableau", "figma", "photoshop", "tensorflow",
        "pytorch", "keras", "scikit-learn", "sklearn",
        "langchain", "llamaindex", "fastapi", "flask",
        "docker", "kubernetes", "aws", "azure", "gcp",
        "simapro", "gabi", "openlca", "autocad",
        "javascript", "react", "html", "css",
        "machine learning", "deep learning",
        "generative ai", "artificial intelligence",
        "data analysis", "data engineering",
    ],

    "Responsibilities and deliverables": [
        "develop", "design", "build", "implement",
        "manage", "maintain", "create", "deliver",
        "analyse", "analyze", "evaluate", "monitor",
        "deploy", "test", "research", "conduct",
        "prepare", "document", "collaborate",
        "support", "lead", "execute", "optimize",
        "optimise", "validate", "integrate",
    ],

    "Experience": [
        "years of experience", "year of experience",
        "experience in", "experience with",
        "professional experience", "fresher",
        "internship", "entry level", "entry-level",
    ],

    "Education and qualifications": [
        "bachelor", "master", "degree",
        "qualification", "graduate", "postgraduate",
        "phd", "diploma", "certification",
        "certified",
    ],

    "Domain knowledge": [
        "sustainability", "finance", "healthcare",
        "automotive", "environmental",
        "life cycle assessment", "lca",
        "user experience", "user interface",
        "cybersecurity", "cloud computing",
        "natural language processing",
        "computer vision", "statistics",
    ],

    "Communication and collaboration": [
        "communication", "teamwork", "collaborate",
        "stakeholder", "client", "presentation",
        "leadership", "interpersonal",
        "problem solving", "problem-solving",
    ],
}
def split_sentences(text):
    text = re.sub(r"\s+"," ",text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])|[•\n\r]+",text)
    cleaned = []
    for part in parts:
        part = part.strip(" \t-–•")
        if len(part) < 12:
            continue
        if part.lower().strip(": ") in STOP_LINES:
            continue
        cleaned.append(part)
    return cleaned
def detect_category(sentence):
    low = sentence.lower()
    scores = {}
    for category, terms in CATEGORY_PATTERNS.items():
        scores[category] = sum(1 for term in terms if term in low)
    best = max(scores,key=scores.get)
    if scores[best] == 0:
        return "Other job requirements"
    return best
def detect_priority(sentence):
    low = sentence.lower()
    mandatory = any(word in low for word in MANDATORY_WORDS)
    preferred = any( word in low for word in PREFERRED_WORDS)
    if mandatory:
        return "Mandatory", 1.5
    if preferred:
        return "Preferred", 0.7
    return "Standard", 1.0
def detect_experience_requirement(sentence):
    low = sentence.lower()
    match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*years?",low)
    if match:
        return (
            f"{match.group(1)} to "
            f"{match.group(2)} years experience"
        )
    match = re.search(r"(?:minimum|at least)\s+(\d+)\s*years?",low)
    if match:
        return (f"At least {match.group(1)} years experience")
    match = re.search(r"(\d+)\+?\s*years?\s+(?:of\s+)?experience",low)
    if match:
        return (f"{match.group(1)} years experience")
    return None
def extract_criteria(jd_text, max_criteria=20):
    sentences = split_sentences(jd_text)
    criteria = []
    seen = set()
    for sentence in sentences:
        low = sentence.lower()
        category = detect_category(sentence)
        if category == "Other job requirements":
            if not any(
                word in low
                for word in [
                    "responsible",
                    "ability",
                    "skill",
                    "knowledge",
                    "experience",
                    "qualification",
                    "proficiency",
                    "familiar",
                    "understanding",
                    "capable",
                    "work independently",
                    "attention to detail",
                ]
            ):

                continue

        normalized = re.sub(r"[^a-z0-9]+"," ",low).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        priority, multiplier = detect_priority(sentence)
        
        action_bonus = 1.15 if any(
            word in low
            for word in [
                "develop",
                "design",
                "build",
                "implement",
                "manage",
                "deliver",
                "execute",
                "deploy",
                "create",
                "conduct",
            ]
        ) else 1.0

        importance = (multiplier * action_bonus)
        criteria.append({
            "criterion_id": (f"C{len(criteria) + 1:02d}"),
            "criterion": sentence,
            "category": category,
            "priority": priority,
            "importance": round(importance,3),
            "weight": 0.0,
            "mandatory_check": (
                priority == "Mandatory"
                or detect_experience_requirement(sentence)
                is not None
            ),
            "experience_requirement":
                detect_experience_requirement(sentence),
            "enabled": True,
        })
        if len(criteria) >= max_criteria:
            break

    if not criteria:
        raise ValueError(
            "Could not identify job requirements. "
            "Please upload a fuller job description."
        )

    total_importance = sum(item["importance"] for item in criteria)
    for item in criteria:
        item["weight"] = round(item["importance"] / total_importance * 100,2)
    difference = round(100 - sum(item["weight"] for item in criteria),2)
    criteria[0]["weight"] += difference
    return criteria

def criteria_dataframe(criteria):
    return pd.DataFrame([
        {
            "Include": item["enabled"],
            "Criterion": item["criterion"],
            "Category": item["category"],
            "Priority": item["priority"],
            "Weight": item["weight"],
            "Mandatory check": item["mandatory_check"],
        }
        for item in criteria
    ])

def apply_edited_criteria(criteria, edited_df):
    updated = []
    for index, row in edited_df.iterrows():
        item = criteria[index].copy()
        item["enabled"] = bool(row["Include"])
        item["weight"] = float(row["Weight"])
        item["mandatory_check"] = bool(row["Mandatory check"])
        updated.append(item)
    active = [item for item in updated if item["enabled"]]
    if not active:
        raise ValueError("At least one criterion must be enabled.")
    total = sum(item["weight"] for item in active)
    if total <= 0:
        raise ValueError("The total criterion weight must be greater than zero.")
    for item in active:
        item["weight"] = (item["weight"] / total * 100)
    return active
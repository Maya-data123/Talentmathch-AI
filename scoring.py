
from __future__ import annotations
import re
from collections import Counter
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
def clean_words(text):
    return set(re.findall(r"[a-z0-9+#.]+",text.lower()))
def resume_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+",text)
    return [x.strip() for x in parts if len(x.strip()) >= 15]

def compare_texts(requirement, evidence):
    if not evidence:
        return 0.0
    try:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True
        )
        matrix = vectorizer.fit_transform([
            requirement,
            evidence
        ])
        tfidf_score = float(
            cosine_similarity(
                matrix[0:1],
                matrix[1:2]
            )[0][0]
        )
    except ValueError:
        tfidf_score = 0.0

    req_words = clean_words(requirement)
    ev_words = clean_words(evidence)
    overlap = (len(req_words & ev_words)/ max(1, len(req_words)))

    char_score = SequenceMatcher(
        None,
        requirement.lower(),
        evidence.lower()
    ).ratio()

    combined = (0.55 * tfidf_score + 0.35 * overlap + 0.10 * char_score)
    return min(1.0,max(0.0,combined))

def find_best_evidence(criterion, sentences):
    results = []
    for sentence in sentences:
        similarity = compare_texts(criterion,sentence)
        results.append((similarity,sentence))
    results.sort(reverse=True,key=lambda x: x[0])
    if not results:
        return 0.0, []
    best_score = results[0][0]
    evidence = [sentence for score, sentence in results[:3] if score >= 0.10]
    return best_score, evidence

def score_candidate(resume_text,criteria,experience_override=None):
    sentences = resume_sentences(resume_text)
    details = []
    weighted_total = 0.0
    mandatory_checks = []
    for item in criteria:
        criterion = item["criterion"]
        weight = float(item["weight"])
        similarity, evidence = find_best_evidence(criterion,sentences)
        if similarity >= 0.65:
            match_level = "Strong evidence"
            match_factor = 1.0
        elif similarity >= 0.42:
            match_level = "Moderate evidence"
            match_factor = 0.75
        elif similarity >= 0.25:
            match_level = "Partial evidence"
            match_factor = 0.50
        elif similarity >= 0.12:
            match_level = "Weak evidence"
            match_factor = 0.25
        else:
            match_level = "Not evidenced"
            match_factor = 0.0
 
        if item.get("experience_requirement"):
            match_level = (
                "Requires experience verification"
            )
            match_factor = min(match_factor,0.5)
            if experience_override is not None:
                match_factor = float(experience_override)
                match_level = ("Manually verified by HR")

        points = round(weight * match_factor,2)
        weighted_total += points
        record = {
            "criterion_id": item["criterion_id"],
            "criterion": criterion,
            "category": item["category"],
            "priority": item["priority"],
            "weight": round(weight, 2),
            "similarity": round(similarity * 100,2),
            "points_awarded": points,
            "match_level": match_level,
            "evidence": evidence,
            "mandatory_check": item["mandatory_check"]
        }
        details.append(record)
        if item["mandatory_check"]:
            mandatory_checks.append({
                "criterion": criterion,
                "status": ("Evidence found; verify manually"
                    if evidence
                    else "Not evidenced; verify manually"
                ),
                "evidence": evidence
            })
    total_weight = sum(float(x["weight"]) for x in criteria)

    overall = (weighted_total / total_weight * 100
        if total_weight
        else 0
    )
    if overall >= 75:
        category = "Strong evidence match"
    elif overall >= 55:
        category = "Moderate evidence match"
    elif overall >= 35:
        category = "Partial evidence match"
    else:
        category = "Limited evidence match"
    return {
        "score": round(overall,2),
        "classification": category,
        "criterion_results": details,
        "mandatory_checks": mandatory_checks,
        "resume_sentence_count": len(sentences)
    }


def rank_resumes(candidates, criteria):
    results = []

    for candidate in candidates:
        result = score_candidate(
            candidate["raw_text"],
            criteria
        )
        results.append({
            "candidate_id": candidate["candidate_id"],
            "filename": candidate["filename"],
            "source": candidate["source"],
            **result
        })
    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank
    return results

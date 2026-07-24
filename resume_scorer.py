ROLE_SKILLS = {
    #------------IT roles 30+----------------------------------------
    'Software Engineer': ['python', 'java', 'c++', 'data structures', 'algorithms'],
    'Frontend Developer': ['html', 'css', 'javascript', 'react', 'bootstrap'],
    'Backend Developer': ['python', 'django', 'flask', 'node.js', 'sql'],
    'Full Stack Developer': ['html', 'css', 'javascript', 'react', 'node.js', 'sql'],

    'Data Scientist': ['python', 'machine learning', 'pandas', 'numpy', 'statistics'],
    'Data Analyst': ['excel', 'sql', 'python', 'power bi', 'data visualization'],
    'Machine Learning Engineer': ['python', 'tensorflow', 'scikit-learn', 'deep learning'],
    'AI Engineer': ['python', 'nlp', 'machine learning', 'deep learning'],

    'DevOps Engineer': ['docker', 'kubernetes', 'aws', 'ci/cd', 'linux'],
    'Cloud Engineer': ['aws', 'azure', 'gcp', 'cloud computing'],
    'Site Reliability Engineer': ['linux', 'monitoring', 'automation', 'aws'],

    'Cyber Security Analyst': ['network security', 'ethical hacking', 'cryptography'],
    'Penetration Tester': ['penetration testing', 'kali linux', 'security tools'],
    'Security Engineer': ['network security', 'firewalls', 'incident response'],

    'Mobile App Developer': ['android', 'kotlin', 'flutter', 'react native'],
    'iOS Developer': ['ios', 'swift', 'xcode'],
    'Android Developer': ['android', 'java', 'kotlin'],

    'UI Designer': ['figma', 'design', 'wireframes'],
    'UX Designer': ['user research', 'prototyping', 'usability testing'],
    'UI/UX Designer': ['figma', 'wireframing', 'prototyping'],

    'QA Engineer': ['testing', 'manual testing', 'bug tracking'],
    'Automation Test Engineer': ['selenium', 'automation testing', 'python'],

    'Database Administrator': ['sql', 'mysql', 'database design', 'backup'],
    'Data Engineer': ['python', 'etl', 'big data', 'spark'],
    'Big Data Engineer': ['hadoop', 'spark', 'data pipelines'],

    'Network Engineer': ['networking', 'routing', 'switching'],
    'System Administrator': ['linux', 'server management', 'networking'],

    'Game Developer': ['unity', 'c#', 'game design'],
    'AR/VR Developer': ['unity', 'c#', '3d modeling'],

    'Blockchain Developer': ['blockchain', 'solidity', 'web3'],
    'Embedded Systems Engineer': ['c', 'microcontrollers', 'embedded systems'],

    'Robotics Engineer': ['robotics', 'python', 'automation'],
    'IoT Engineer': ['iot', 'sensors', 'embedded systems'],

    'Technical Support Engineer': ['troubleshooting', 'networking', 'support'],
    'IT Support Specialist': ['hardware', 'software', 'troubleshooting'],

    'Solutions Architect': ['system design', 'cloud', 'architecture'],
    'Software Architect': ['design patterns', 'system design', 'scalability'],

    # 🔥 NON-IT ROLES (20+ added properly)

    'HR Executive': ['recruitment', 'communication', 'ms office', 'employee engagement'],
    'HR Manager': ['recruitment', 'leadership', 'performance management', 'hr policies'],

    'Digital Marketing Executive': ['seo', 'sem', 'social media', 'content marketing'],
    'Marketing Manager': ['branding', 'campaign management', 'market research', 'strategy'],

    'Sales Executive': ['communication', 'negotiation', 'lead generation', 'crm'],
    'Sales Manager': ['sales strategy', 'team management', 'target achievement'],

    'Accountant': ['accounting', 'tally', 'gst', 'financial statements'],
    'Financial Analyst': ['excel', 'financial modeling', 'analysis', 'forecasting'],

    'Operations Executive': ['operations', 'coordination', 'ms office', 'reporting'],
    'Operations Manager': ['project management', 'supply chain', 'leadership'],

    'Business Analyst': ['requirements analysis', 'communication', 'sql', 'documentation'],
    'Product Manager': ['product strategy', 'roadmap', 'agile', 'stakeholder management'],

    'Customer Support Executive': ['communication', 'problem solving', 'crm'],
    'Customer Success Manager': ['client handling', 'relationship management', 'support'],

    'Content Writer': ['writing', 'editing', 'seo', 'creativity'],
    'Copywriter': ['copywriting', 'marketing', 'branding', 'creativity'],

    'Graphic Designer': ['photoshop', 'illustrator', 'creativity', 'design'],
    'Video Editor': ['video editing', 'premiere pro', 'after effects'],

    'Teacher': ['teaching', 'communication', 'subject knowledge'],
    'Trainer': ['training', 'presentation', 'communication'],

    'Administrative Assistant': ['ms office', 'organization', 'communication'],
    'Office Manager': ['administration', 'coordination', 'management'],

    'Logistics Coordinator': ['logistics', 'supply chain', 'coordination'],
    'Supply Chain Analyst': ['supply chain', 'data analysis', 'planning'],

}

ACTION_KEYWORDS = [
    'developed', 'built', 'designed', 'implemented', 'created', 'managed', 'led',
    'analyzed', 'optimized', 'improved', 'achieved', 'delivered', 'coordinated',
    'collaborated', 'mentored', 'automated', 'deployed', 'tested', 'maintained',
    'researched', 'presented', 'trained', 'executed', 'launched', 'increased',
]

REQUIRED_SECTIONS = {
    'education': ['education', 'academic', 'degree', 'university', 'college', 'school'],
    'projects': ['project', 'projects', 'work sample'],
    'experience': ['experience', 'internship', 'work experience', 'employment', 'intern'],
}

def score_resume(text, role):
    text_lower = text.lower()

    # 1. Skills Score (40 pts)
    role_skill_list = ROLE_SKILLS.get(role, ['communication', 'problem solving'])
    matched_skills = [s for s in role_skill_list if s in text_lower]
    skills_score = min(40, int((len(matched_skills) / len(role_skill_list)) * 40))
    missing_skills = [s for s in role_skill_list if s not in text_lower]

    # 2. Keywords Score (30 pts)
    matched_keywords = [kw for kw in ACTION_KEYWORDS if kw in text_lower]
    keywords_score = min(30, int((len(matched_keywords) / 10) * 30))

    # 3. Sections Score (30 pts)
    section_scores = {}
    sections_found = []
    sections_missing = []
    per_section = 30 // len(REQUIRED_SECTIONS)

    for section, patterns in REQUIRED_SECTIONS.items():
        found = any(p in text_lower for p in patterns)
        if found:
            sections_found.append(section)
            section_scores[section] = per_section
        else:
            sections_missing.append(section)
            section_scores[section] = 0

    sections_score = sum(section_scores.values())

    # 🔥 TOTAL
    total = skills_score + keywords_score + sections_score

    # 🔥 STATUS (NOW CORRECT POSITION)
    if total < 60:
        status = "Needs Improvement"
    elif total < 75:
        status = "Average"
    elif total < 85:
        status = "Good"
    else:
        status = "Excellent"

    # Suggestions
    suggestions = []
    if missing_skills:
        suggestions.append(f"Add role-relevant skills: {', '.join(missing_skills[:4])}")
    if 'projects' in sections_missing:
        suggestions.append("Add a Projects section")
    if 'experience' in sections_missing:
        suggestions.append("Add an Experience section")
    if keywords_score < 15:
        suggestions.append("Use more action verbs")

    # Reasons
    reasons = []
    if 'projects' in sections_missing:
        reasons.append("Missing Projects section")
    if 'experience' in sections_missing:
        reasons.append("No Experience found")

    # ✅ FINAL RETURN (ONLY ONE)
    return {
        'total': total,
        'skills_score': skills_score,
        'keywords_score': keywords_score,
        'sections_score': sections_score,
        'matched_skills': matched_skills,
        'missing_skills': missing_skills[:6],
        'sections_found': sections_found,
        'sections_missing': sections_missing,
        'suggestions': suggestions,
        'reasons': reasons,
        'pass': total >= 60,
        'status': status,
        'ready_for_jobs': total >= 70
    }
import re

ALL_SKILLS = [
    # IT
    'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 'swift', 'kotlin',
    'react', 'angular', 'vue', 'node.js', 'nodejs', 'express', 'django', 'flask', 'fastapi',
    'spring', 'hibernate', 'html', 'css', 'bootstrap', 'tailwind',
    'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'sqlite', 'oracle',
    'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'keras', 'scikit-learn',
    'nlp', 'computer vision', 'data science', 'pandas', 'numpy', 'matplotlib', 'seaborn',
    'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'git', 'github', 'ci/cd',
    'rest api', 'graphql', 'microservices', 'linux', 'bash', 'powershell',
    'android', 'ios', 'react native', 'flutter',
    'selenium', 'pytest', 'junit', 'agile', 'scrum',
    # Data
    'tableau', 'power bi', 'excel', 'r', 'spss', 'hadoop', 'spark', 'airflow',
    # Non-IT
    'recruitment', 'communication', 'leadership', 'teamwork', 'problem solving',
    'ms office', 'word', 'powerpoint',
    'seo', 'sem', 'google analytics', 'social media', 'content marketing', 'branding',
    'digital marketing', 'email marketing', 'copywriting', 'market research',
    'accounting', 'tally', 'finance', 'budgeting', 'financial modeling', 'taxation',
    'auditing', 'gst', 'erp', 'sap',
    'project management', 'operations', 'supply chain', 'logistics',
    'customer service', 'sales', 'negotiation', 'presentation',
]

def extract_skills(text):
    """Extract skills from resume text."""
    text_lower = text.lower()
    found = []
    for skill in ALL_SKILLS:
        if skill in text_lower and skill not in found:
            found.append(skill)
    return found

import csv
import json
import os
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

try:
    from ollama import chat
except ImportError:
    print("Please install Ollama first: pip install ollama")
    sys.exit(1)


@dataclass
class CompanyData:
    """Data structure for company information"""
    name: str
    website: str
    industry: str
    size: str
    location: str
    core_problem: str = ""
    pain_points: List[str] = field(default_factory=list)
    recent_news: str = ""


@dataclass
class ResumeData:
    """Data structure for resume information"""
    name: str
    email: str
    phone: str
    skills: List[str]
    past_projects: List[Dict]
    certifications: List[str]
    interests: List[str]
    writing_style: Dict


class ResearcherAgent:
    """Agent that researches companies and extracts core problems"""
    
    def __init__(self, model: str = "qwen3.5"):
        self.model = model
        self.system_prompt = """You are a professional business researcher. 
        Your task is to analyze company websites and extract their core problems, 
        pain points, and business challenges. Be specific and actionable.
        
        Focus on:
        1. What problems does this company face?
        2. What are their main pain points?
        3. What industry trends affect them?
        4. What solutions might they need?
        
        Keep responses concise and relevant for cold email purposes."""
    
    def research_company(self, company: CompanyData) -> CompanyData:
        """Research a company and extract core problems"""
        
        # Create research prompt
        prompt = f"""Based on this company information:
        Name: {company.name}
        Website: {company.website}
        Industry: {company.industry}
        Size: {company.size}
        Location: {company.location}
        
        Research this company and identify:
        1. Their core business problem
        2. Key pain points
        3. Recent challenges or news
        
        Provide specific, actionable insights that would be relevant for a cold email.
        Keep it under 200 words."""
        
        try:
            response = chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse the response safely
            if not response or 'message' not in response:
                print("Warning: Empty response from Ollama")
                company.core_problem = "Need to identify specific business challenges"
                company.pain_points = ["General industry challenges", "Market competition"]
                return company
            
            research_result = response.get('message', {}).get('content', '')
            
            # Extract key information from research
            company.core_problem = self._extract_core_problem(research_result)
            company.pain_points = self._extract_pain_points(research_result)
            
            return company
            
        except Exception as e:
            print(f"Research error: {e}")
            # Return company with default research
            company.core_problem = "Need to identify specific business challenges"
            company.pain_points = ["General industry challenges", "Market competition"]
            return company
    
    def _extract_core_problem(self, text: str) -> str:
        """Extract core problem from research text"""
        # Simple extraction - in production, use more sophisticated parsing
        if not text or len(text) == 0:
            return "Core business challenge needs identification"
        
        text_lower = text.lower()
        if "problem" in text_lower:
            parts = text.split("problem")
            if len(parts) > 1:
                try:
                    return parts[1].split(".")[0].strip()[:100]
                except (IndexError, AttributeError):
                    return "Core business challenge needs identification"
        
        # Try alternative keywords
        keywords = ["challenge", "issue", "struggle", "difficulty", "concern"]
        for keyword in keywords:
            if keyword in text_lower:
                parts = text.split(keyword)
                if len(parts) > 1:
                    try:
                        return parts[1].split(".")[0].strip()[:100]
                    except (IndexError, AttributeError):
                        return "Core business challenge needs identification"
        
        return "Core business challenge needs identification"
    
    def _extract_pain_points(self, text: str) -> List[str]:
        """Extract pain points from research text"""
        points = []
        
        if not text or len(text) == 0:
            return ["General operational challenges"]
        
        text_lower = text.lower()
        if "pain" in text_lower or "challenge" in text_lower:
            # Extract pain points
            lines = text.split("\n")
            for line in lines:
                line_lower = line.lower()
                if "pain" in line_lower or "challenge" in line_lower:
                    try:
                        point = line.strip()[:100]
                        if point:
                            points.append(point)
                    except (IndexError, AttributeError):
                        continue
        
        # If no pain points found, use defaults
        if not points:
            points = ["General operational challenges", "Market competition", "Customer retention"]
        
        return points[:5]


class CopywriterAgent:
    """Agent that writes personalized cold emails"""
    
    def __init__(self, model: str = "qwen3.5"):
        self.model = model
        self.system_prompt = """You are an expert copywriter specializing in personalized cold emails.
        Your goal is to write highly relevant, personalized emails that:
        1. Show you've researched the company
        2. Connect their pain points to your solutions
        3. Use a professional yet conversational tone
        4. Include relevant skills from the sender's resume
        5. Keep it under 150 words
        6. Include a clear call to action
        
        Write emails that feel authentic and not templated."""
    
    def write_email(self, company: CompanyData, resume: ResumeData, 
                    additional_interests: Optional[str] = None) -> str:
        """Write a personalized cold email"""
        
        # Build the email prompt
        prompt = self._build_email_prompt(company, resume, additional_interests)
        
        try:
            response = chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse the response safely
            if not response or 'message' not in response:
                print("Warning: Empty response from Ollama")
                return self._fallback_email(company, resume)
            
            return response.get('message', {}).get('content', self._fallback_email(company, resume))
            
        except Exception as e:
            print(f"Copywriting error: {e}")
            return self._fallback_email(company, resume)
    
    def _build_email_prompt(self, company: CompanyData, resume: ResumeData,
                           additional_interests: Optional[str]) -> str:
        """Build the email writing prompt"""
        
        # Find matching skills
        matching_skills = self._find_skill_matches(company, resume)
        
        # Build company context
        company_context = f"""Company: {company.name}
Industry: {company.industry}
Size: {company.size}
Location: {company.location}
Core Problem: {company.core_problem}
Pain Points: {', '.join(company.pain_points)}"""
        
        # Build resume context
        resume_context = f"""Your Skills: {', '.join(resume.skills)}
Your Projects: {len(resume.past_projects)} relevant projects
Your Interests: {', '.join(resume.interests)}"""
        
        # Add additional interests if provided
        if additional_interests:
            resume_context += f"\nAdditional Interests: {additional_interests}"
        
        prompt = f"""Write a personalized cold email to a decision maker at:
        
{company_context}

{resume_context}

Your writing style: {resume.writing_style.get('tone', 'professional')}
Your writing style: {resume.writing_style.get('length', 'concise')}

Requirements:
- Address their specific pain point
- Mention 1-2 relevant skills from your resume
- Keep it under 150 words
- Include a clear call to action
- Make it sound authentic and personalized

Write the email now:"""
        
        return prompt
    
    def _find_skill_matches(self, company: CompanyData, resume: ResumeData) -> List[str]:
        """Find skills that match company needs"""
        matches = []
        company_keywords = [p.lower() for p in company.pain_points]
        
        for skill in resume.skills:
            skill_lower = skill.lower()
            for keyword in company_keywords:
                if keyword in skill_lower or skill_lower in keyword:
                    matches.append(skill)
                    break
        
        return matches[:3] if matches else resume.skills[:3]
    
    def _fallback_email(self, company: CompanyData, resume: ResumeData) -> str:
        """Generate a fallback email if LLM fails"""
        return f"""Hi {company.name} Team,

I noticed you're facing challenges in {company.industry}. 

With my experience in {', '.join(resume.skills[:3])}, I've helped similar companies overcome {company.core_problem}.

I'd love to discuss how we can help.

Best,
{resume.name}"""


class ColdEmailer:
    """Main orchestrator for the cold emailer system"""
    
    def __init__(self, model: str = "qwen3.5", resume_file: str = "resume.json"):
        self.model = model
        self.resume_file = resume_file
        self.researcher = ResearcherAgent(model)
        self.copywriter = CopywriterAgent(model)
        self.resume_data: Optional[ResumeData] = None
        self.writing_habits = {
            'tone': 'professional yet conversational',
            'length': 'concise',
            'signature': 'Best regards,',
            'max_words': 150
        }
    
    def load_resume(self) -> bool:
        """Load resume data from JSON file"""
        if not os.path.exists(self.resume_file):
            print(f"Resume file not found: {self.resume_file}")
            print("Creating default resume...")
            self.create_default_resume()
            return True
        
        try:
            with open(self.resume_file, 'r') as f:
                data = json.load(f)
            
            self.resume_data = ResumeData(
                name=data.get('name', 'Your Name'),
                email=data.get('email', ''),
                phone=data.get('phone', ''),
                skills=data.get('skills', []),
                past_projects=data.get('projects', []),
                certifications=data.get('certifications', []),
                interests=data.get('interests', []),
                writing_style=data.get('writing_style', self.writing_habits)
            )
            
            print(f"Loaded resume for {self.resume_data.name}")
            return True
            
        except Exception as e:
            print(f"Error loading resume: {e}")
            self.create_default_resume()
            return False
    
    def create_default_resume(self):
        """Create a default resume if none exists"""
        default_resume = {
            'name': 'Your Name',
            'email': 'your.email@example.com',
            'phone': '',
            'skills': ['Python', 'Data Analysis', 'Project Management', 'Communication'],
            'projects': [
                {'name': 'Project 1', 'description': 'Description of project'},
                {'name': 'Project 2', 'description': 'Description of project'}
            ],
            'certifications': [],
            'interests': ['Technology', 'Innovation', 'Leadership'],
            'writing_style': {
                'tone': 'professional yet conversational',
                'length': 'concise',
                'signature': 'Best regards,'
            }
        }
        
        with open(self.resume_file, 'w') as f:
            json.dump(default_resume, f, indent=2)
        
        self.resume_data = ResumeData(
            name=default_resume['name'],
            email=default_resume['email'],
            phone=default_resume['phone'],
            skills=default_resume['skills'],
            past_projects=default_resume['projects'],
            certifications=default_resume['certifications'],
            interests=default_resume['interests'],
            writing_style=default_resume['writing_style']
        )
    
    def create_mock_csv(self, filename: str = "companies.csv") -> bool:
        """Create a mock CSV file with sample companies"""
        sample_companies = [
            {'name': 'TechCorp Inc.', 'website': 'https://techcorp.com', 
             'industry': 'Technology', 'size': '500-1000', 'location': 'San Francisco, CA'},
            {'name': 'GreenEnergy Solutions', 'website': 'https://greenenergy.com',
             'industry': 'Renewable Energy', 'size': '100-500', 'location': 'Austin, TX'},
            {'name': 'HealthFirst Medical', 'website': 'https://healthfirst.com',
             'industry': 'Healthcare', 'size': '1000+', 'location': 'Boston, MA'},
            {'name': 'EduLearn Platform', 'website': 'https://edulearn.com',
             'industry': 'Education', 'size': '50-100', 'location': 'New York, NY'},
            {'name': 'RetailMax', 'website': 'https://retailmax.com',
             'industry': 'Retail', 'size': '200-500', 'location': 'Chicago, IL'}
        ]
        
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'website', 'industry', 'size', 'location'])
            writer.writeheader()
            writer.writerows(sample_companies)
        
        print(f"Created mock CSV: {filename}")
        return True
    
    def process_company(self, company_name: str) -> Optional[str]:
        """Process a single company and generate email"""
        
        # Load resume if not loaded
        if not self.resume_data:
            self.load_resume()
        
        # Create or load company data
        company = CompanyData(
            name=company_name,
            website=f"https://{company_name.lower().replace(' ', '').replace('.', '')}.com",
            industry="Technology",
            size="100-500",
            location="Unknown"
        )
        
        # Research the company
        print(f"\n🔍 Researching: {company.name}")
        company = self.researcher.research_company(company)
        
        # Ask for additional interests
        additional_interests = self._ask_additional_interests()
        
        # Write the email
        print(f"\n✍️ Writing email for: {company.name}")
        email = self.copywriter.write_email(company, self.resume_data, additional_interests)
        
        return email
    
    def process_all_companies(self, csv_file: str = "companies.csv") -> List[str]:
        """Process all companies from CSV file"""
        
        if not os.path.exists(csv_file):
            print(f"CSV file not found: {csv_file}")
            print("Creating mock CSV...")
            self.create_mock_csv(csv_file)
        
        emails = []
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                company = CompanyData(
                    name=row['name'],
                    website=row['website'],
                    industry=row['industry'],
                    size=row['size'],
                    location=row['location']
                )
                
                email = self.process_company(company.name)
                if email:
                    emails.append(email)
                    print(f"\n{'='*60}")
                    print(f"Generated email for: {company.name}")
                    print(f"{'='*60}")
                    print(email)
                    print(f"{'='*60}\n")
        
        return emails
    
    def _ask_additional_interests(self) -> str:
        """Prompt user for additional interests"""
        print("\n💡 Would you like to add any personal interests to this email?")
        print("   (e.g., hobbies, shared interests, recent events)")
        print("   Type 'yes' to add, 'no' to skip, or enter your interests directly:")
        
        response = input("\nYour input: ").strip()
        
        if response.lower() == 'yes':
            interests = input("Enter your interests (comma-separated): ").strip()
            return interests
        elif response.lower() == 'no':
            return ""
        else:
            return response
    
    def save_email(self, email: str, filename: str = "email.txt"):
        """Save email to file"""
        with open(filename, 'w') as f:
            f.write(email)
        print(f"\n✅ Email saved to: {filename}")


def main():
    """Main function to run the cold emailer"""
    print("="*60)
    print("🚀 Multi-Agent Cold Emailer")
    print("="*60)
    print("\nThis tool uses Ollama to create personalized cold emails.")
    print("Make sure Ollama is running and you have a model loaded.\n")
    
    # Create the emailer
    emailer = ColdEmailer(model="qwen3.5")
    
    # Load resume
    emailer.load_resume()
    
    # Process companies
    print("\n📋 Processing companies from CSV...")
    emails = emailer.process_all_companies()
    
    # Save all emails
    if emails:
        with open("all_emails.txt", 'w') as f:
            for email in emails:
                f.write(email + "\n\n" + "="*60 + "\n\n")
        print(f"\n📁 All emails saved to: all_emails.txt")
    
    print("\n" + "="*60)
    print("✅ Cold emailer completed!")
    print("="*60)


if __name__ == "__main__":
    main()

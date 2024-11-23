from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool
from models import LinkedInResearchOutput
from dotenv import load_dotenv

load_dotenv()

@CrewBase
class LatestAiDevelopmentCrew():
    """LatestAiDevelopment crew"""

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config['researcher'],
            verbose=False,
            tools=[SerperDevTool()],
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['reporting_analyst'],
            verbose=False
        )

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config['research_task'],
        )

    @task
    def reporting_task(self) -> Task:
        return Task(
            config=self.tasks_config['reporting_task'],
            output_json=LinkedInResearchOutput
            
        )

    @crew
    def crew(self) -> Crew:
        """Creates the LatestAiDevelopment crew"""
        if hasattr(self, 'inputs') and 'language' in self.inputs:
            self.agents['researcher'].tools = [SerperDevTool(country=self.inputs['language'])]
        
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False
        )
"""
Timmy's Skill Absorption System

Allows Timmy to dynamically load, parse, and integrate new skills into his
knowledge base and capabilities. Skills are self-contained packages that extend
Timmy's abilities through specialized workflows, tools, and domain expertise.

Architecture:
- Skill Discovery: Scan for .skill files or skill directories
- Skill Parsing: Extract metadata, resources, and instructions from SKILL.md
- Skill Integration: Merge into memory (vault), tools, and agent capabilities
- Skill Execution: Execute scripts and apply templates as needed
"""

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any
from zipfile import ZipFile

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILLS_VAULT_PATH = PROJECT_ROOT / "memory" / "skills"
SKILLS_VAULT_PATH.mkdir(parents=True, exist_ok=True)


@dataclass
class SkillMetadata:
    """Parsed skill metadata from SKILL.md frontmatter."""
    name: str
    description: str
    license: Optional[str] = None
    absorbed_at: Optional[str] = None
    source_path: Optional[str] = None


@dataclass
class SkillResources:
    """Parsed skill resources."""
    scripts: Dict[str, str]  # filename -> content
    references: Dict[str, str]  # filename -> content
    templates: Dict[str, str]  # filename -> content


class SkillParser:
    """Parses skill packages and extracts metadata and resources."""
    
    @staticmethod
    def parse_skill_md(skill_md_path: Path) -> tuple[SkillMetadata, str]:
        """
        Parse SKILL.md and extract frontmatter metadata and body content.
        
        Returns:
            Tuple of (SkillMetadata, body_content)
        """
        content = skill_md_path.read_text()
        
        # Extract YAML frontmatter
        if not content.startswith("---"):
            raise ValueError(f"Invalid SKILL.md: missing frontmatter at {skill_md_path}")
        
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid SKILL.md: malformed frontmatter at {skill_md_path}")
        
        try:
            metadata_dict = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in SKILL.md: {e}") from e
        
        # Create metadata object
        metadata = SkillMetadata(
            name=metadata_dict.get("name"),
            description=metadata_dict.get("description"),
            license=metadata_dict.get("license"),
            absorbed_at=datetime.now(timezone.utc).isoformat(),
            source_path=str(skill_md_path),
        )
        
        if not metadata.name or not metadata.description:
            raise ValueError("SKILL.md must have 'name' and 'description' fields")
        
        body_content = parts[2].strip()
        return metadata, body_content
    
    @staticmethod
    def load_resources(skill_dir: Path) -> SkillResources:
        """Load all resources from a skill directory."""
        resources = SkillResources(scripts={}, references={}, templates={})
        
        # Load scripts
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.glob("*"):
                if script_file.is_file() and not script_file.name.startswith("."):
                    resources.scripts[script_file.name] = script_file.read_text()
        
        # Load references
        references_dir = skill_dir / "references"
        if references_dir.exists():
            for ref_file in references_dir.glob("*"):
                if ref_file.is_file() and not ref_file.name.startswith("."):
                    resources.references[ref_file.name] = ref_file.read_text()
        
        # Load templates
        templates_dir = skill_dir / "templates"
        if templates_dir.exists():
            for template_file in templates_dir.glob("*"):
                if template_file.is_file() and not template_file.name.startswith("."):
                    resources.templates[template_file.name] = template_file.read_text()
        
        return resources


class SkillAbsorber:
    """Absorbs skills into Timmy's knowledge base and capabilities."""
    
    def __init__(self):
        self.vault_path = SKILLS_VAULT_PATH
        self.absorbed_skills: Dict[str, SkillMetadata] = {}
        self._load_absorbed_skills_index()
    
    def _load_absorbed_skills_index(self) -> None:
        """Load the index of previously absorbed skills."""
        index_path = self.vault_path / "index.json"
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text())
                for skill_name, metadata_dict in data.items():
                    self.absorbed_skills[skill_name] = SkillMetadata(**metadata_dict)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to load skills index: {e}")
    
    def _save_absorbed_skills_index(self) -> None:
        """Save the index of absorbed skills."""
        index_path = self.vault_path / "index.json"
        data = {name: asdict(meta) for name, meta in self.absorbed_skills.items()}
        index_path.write_text(json.dumps(data, indent=2))
    
    def absorb_skill(self, skill_path: Path) -> SkillMetadata:
        """
        Absorb a skill from a file or directory.
        
        Args:
            skill_path: Path to .skill file or skill directory
        
        Returns:
            SkillMetadata of the absorbed skill
        """
        # Handle .skill files (zip archives)
        if skill_path.suffix == ".skill":
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                with ZipFile(skill_path) as zf:
                    zf.extractall(tmpdir_path)
                return self._absorb_skill_directory(tmpdir_path)
        
        # Handle skill directories
        elif skill_path.is_dir():
            return self._absorb_skill_directory(skill_path)
        
        else:
            raise ValueError(f"Invalid skill path: {skill_path}")
    
    def _absorb_skill_directory(self, skill_dir: Path) -> SkillMetadata:
        """Absorb a skill from a directory."""
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise ValueError(f"Skill directory missing SKILL.md: {skill_dir}")
        
        # Parse metadata and content
        metadata, body_content = SkillParser.parse_skill_md(skill_md)
        
        # Load resources
        resources = SkillParser.load_resources(skill_dir)
        
        # Store in vault
        skill_vault_dir = self.vault_path / metadata.name
        skill_vault_dir.mkdir(parents=True, exist_ok=True)
        
        # Save metadata
        metadata_path = skill_vault_dir / "metadata.json"
        metadata_path.write_text(json.dumps(asdict(metadata), indent=2))
        
        # Save SKILL.md content
        content_path = skill_vault_dir / "content.md"
        content_path.write_text(body_content)
        
        # Save resources
        for resource_type, files in [
            ("scripts", resources.scripts),
            ("references", resources.references),
            ("templates", resources.templates),
        ]:
            resource_dir = skill_vault_dir / resource_type
            resource_dir.mkdir(exist_ok=True)
            for filename, content in files.items():
                (resource_dir / filename).write_text(content)
        
        # Update index
        self.absorbed_skills[metadata.name] = metadata
        self._save_absorbed_skills_index()
        
        logger.info(f"✓ Absorbed skill: {metadata.name}")
        return metadata
    
    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve an absorbed skill's full data."""
        if skill_name not in self.absorbed_skills:
            return None
        
        skill_dir = self.vault_path / skill_name
        
        # Load metadata
        metadata_path = skill_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        
        # Load content
        content_path = skill_dir / "content.md"
        content = content_path.read_text() if content_path.exists() else ""
        
        # Load resources
        resources = {
            "scripts": {},
            "references": {},
            "templates": {},
        }
        
        for resource_type in resources.keys():
            resource_dir = skill_dir / resource_type
            if resource_dir.exists():
                for file in resource_dir.glob("*"):
                    if file.is_file():
                        resources[resource_type][file.name] = file.read_text()
        
        return {
            "metadata": metadata,
            "content": content,
            "resources": resources,
        }
    
    def list_skills(self) -> List[SkillMetadata]:
        """List all absorbed skills."""
        return list(self.absorbed_skills.values())
    
    def export_skill_to_memory(self, skill_name: str) -> str:
        """
        Export a skill's content to a memory vault entry format.
        
        Returns:
            Formatted markdown for insertion into memory vault
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return ""
        
        metadata = skill["metadata"]
        content = skill["content"]
        
        # Format as memory entry
        entry = f"""# Skill: {metadata['name']}

**Absorbed:** {metadata['absorbed_at']}

## Description
{metadata['description']}

## Content
{content}

## Resources Available
- Scripts: {', '.join(skill['resources']['scripts'].keys()) or 'None'}
- References: {', '.join(skill['resources']['references'].keys()) or 'None'}
- Templates: {', '.join(skill['resources']['templates'].keys()) or 'None'}
"""
        return entry
    
    def execute_skill_script(self, skill_name: str, script_name: str, **kwargs) -> str:
        """
        Execute a script from an absorbed skill.
        
        Args:
            skill_name: Name of the skill
            script_name: Name of the script file
            **kwargs: Arguments to pass to the script
        
        Returns:
            Script output
        """
        skill = self.get_skill(skill_name)
        if not skill or script_name not in skill["resources"]["scripts"]:
            raise ValueError(f"Script not found: {skill_name}/{script_name}")
        
        script_content = skill["resources"]["scripts"][script_name]
        
        # Execute script (Python only for now)
        if script_name.endswith(".py"):
            import subprocess
            result = subprocess.run(
                ["python", "-c", script_content],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.stdout or result.stderr
        
        raise ValueError(f"Unsupported script type: {script_name}")


# Singleton instance
_absorber: Optional[SkillAbsorber] = None


def get_skill_absorber() -> SkillAbsorber:
    """Get or create the skill absorber singleton."""
    global _absorber
    if _absorber is None:
        _absorber = SkillAbsorber()
    return _absorber

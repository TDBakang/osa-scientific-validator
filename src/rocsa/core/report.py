from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from rocsa.core.context import CSAContext
from rocsa.core.result import CSAResult, CSAStatus
from rocsa_generator.models.csa import CSAFamily, CSASeverity


class SeveritySummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0


class FamilySummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    compliance_rate: float = 0.0


class CSAReport(BaseModel):
    report_id: str
    execution_id: str
    target_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    total_controls: int = 0
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    
    global_score: float = 0.0
    compliance_rate: float = 0.0
    total_execution_time_ms: float = 0.0
    
    by_severity: Dict[str, SeveritySummary] = Field(default_factory=dict)
    by_family: Dict[str, FamilySummary] = Field(default_factory=dict)
    
    critical_failures: List[str] = Field(default_factory=list)
    consolidated_recommendations: List[str] = Field(default_factory=list)
    results: List[CSAResult] = Field(default_factory=list)

    @classmethod
    def generate(cls, context: CSAContext, results: List[CSAResult], report_id: Optional[str] = None) -> "CSAReport":
        rep_id = report_id or f"REP-{context.execution_id}"
        total = len(results)
        passed = sum(1 for r in results if r.status == CSAStatus.PASS)
        failed = sum(1 for r in results if r.status == CSAStatus.FAIL)
        skipped = sum(1 for r in results if r.status == CSAStatus.SKIPPED)
        error = sum(1 for r in results if r.status == CSAStatus.ERROR)
        
        compliance_rate = (passed / total * 100.0) if total > 0 else 0.0
        global_score = (sum(r.score for r in results) / total) if total > 0 else 0.0
        total_time = sum(r.execution_time_ms for r in results)
        
        by_sev: Dict[str, SeveritySummary] = {}
        for sev in CSASeverity:
            sev_results = [r for r in results if r.severity == sev]
            if sev_results:
                by_sev[sev.value] = SeveritySummary(
                    total=len(sev_results),
                    passed=sum(1 for r in sev_results if r.status == CSAStatus.PASS),
                    failed=sum(1 for r in sev_results if r.status == CSAStatus.FAIL),
                    error=sum(1 for r in sev_results if r.status == CSAStatus.ERROR),
                )
                
        by_fam: Dict[str, FamilySummary] = {}
        for fam in CSAFamily:
            fam_results = [r for r in results if r.family == fam]
            if fam_results:
                f_passed = sum(1 for r in fam_results if r.status == CSAStatus.PASS)
                f_total = len(fam_results)
                by_fam[fam.value] = FamilySummary(
                    total=f_total,
                    passed=f_passed,
                    failed=sum(1 for r in fam_results if r.status == CSAStatus.FAIL),
                    compliance_rate=(f_passed / f_total * 100.0) if f_total > 0 else 0.0,
                )
                
        crit_failures = []
        recs = []
        for r in results:
            if r.status in [CSAStatus.FAIL, CSAStatus.ERROR]:
                if r.severity in [CSASeverity.CRITICAL, CSASeverity.HIGH]:
                    crit_failures.append(f"[{r.control_id}] {r.title} ({r.severity.value}) : {r.summary}")
            recs.extend(r.recommendations)
            
        return cls(
            report_id=rep_id,
            execution_id=context.execution_id,
            target_name=context.target_name,
            timestamp=context.timestamp,
            total_controls=total,
            passed_count=passed,
            failed_count=failed,
            skipped_count=skipped,
            error_count=error,
            global_score=round(global_score, 4),
            compliance_rate=round(compliance_rate, 2),
            total_execution_time_ms=round(total_time, 3),
            by_severity=by_sev,
            by_family=by_fam,
            critical_failures=crit_failures,
            consolidated_recommendations=list(set(recs)),
            results=results,
        )

    def summary_text(self) -> str:
        lines = [
            "=== RAPPORT D'AUDIT SCIENTIFIQUE ROCSA ===",
            f"ID Rapport     : {self.report_id}",
            f"Cible          : {self.target_name}",
            f"Execution ID   : {self.execution_id}",
            f"Taux Conformite: {self.compliance_rate}%",
            f"Score Global   : {self.global_score} / 1.0",
            f"Controles      : {self.total_controls} au total ({self.passed_count} PASSED, {self.failed_count} FAILED, {self.error_count} ERROR)",
            f"Temps de Calcul: {self.total_execution_time_ms:.2f} ms",
        ]
        if self.critical_failures:
            lines.append("")
            lines.append("DEFAILLANCES CRITIQUES / HAUTES :")
            for cf in self.critical_failures:
                lines.append(f"  - {cf}")
        return "\n".join(lines)

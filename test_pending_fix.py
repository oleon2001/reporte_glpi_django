#!/usr/bin/env python3
"""
Test script to verify the pending tickets calculation fix
"""

import os
import sys
import django
from datetime import date, timedelta
import calendar

# Add the project directory to Python path
sys.path.append('/home/oleon/Escritorio/reporte_glpi_django')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reporte_glpi_django.settings')
django.setup()

from metricas.services import ReportGenerator

def test_pending_tickets_calculation():
    """Test the fixed pending tickets calculation"""
    print("🔍 Testing pending tickets calculation fix...")
    
    # Use current month for testing
    today = date.today()
    fecha_ini = date(today.year, today.month, 1).strftime('%Y-%m-%d')
    _, last_day = calendar.monthrange(today.year, today.month)
    fecha_fin = date(today.year, today.month, last_day).strftime('%Y-%m-%d')
    
    print(f"📅 Testing period: {fecha_ini} to {fecha_fin}")
    
    try:
        # Test the fixed SLA metrics query
        print("\n🧪 Testing SLA metrics query...")
        sla_results = ReportGenerator._execute_optimized_query_sla_metrics(fecha_ini, fecha_fin)
        
        if not sla_results.empty:
            print("✅ SLA metrics query executed successfully")
            print(f"📊 Found {len(sla_results)} technicians with SLA data")
            print("\nSample results:")
            print(sla_results.head().to_string())
            
            # Check if pending tickets are calculated
            pending_total = sla_results['pendientes_sla'].sum()
            print(f"\n📈 Total pending tickets with SLA issues: {pending_total}")
            
        else:
            print("⚠️  No SLA data found for the test period")
        
        # Test the complete report generation
        print("\n🧪 Testing complete report generation...")
        report_results = ReportGenerator.generar_reporte_principal(fecha_ini, fecha_fin)
        
        if report_results:
            print("✅ Complete report generated successfully")
            print(f"📊 Found {len(report_results)} technicians in report")
            
            # Show sample technician data
            if report_results:
                sample = report_results[0]
                print(f"\nSample technician data:")
                print(f"- Technician: {sample.get('Tecnico_Asignado', 'N/A')}")
                print(f"- Tickets received: {sample.get('Cant_tickets_recibidos', 0)}")
                print(f"- Tickets closed: {sample.get('Cant_tickets_cerrados', 0)}")
                print(f"- Closed within SLA: {sample.get('Cerrados_dentro_SLA', 0)}")
                print(f"- Closed with SLA: {sample.get('Cerrados_con_SLA', 0)}")
                print(f"- Pending SLA: {sample.get('tickets_pendientes_SLA', 0)}")
                print(f"- SLA Compliance: {sample.get('Cumplimiento SLA', 0)}%")
        else:
            print("⚠️  No report data found for the test period")
            
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pending_tickets_calculation() 
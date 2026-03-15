import os
import re

def final_scripts_fix():
    path = r"c:\Users\argen\Documents\LUBMOVIL\app\templates\index.html"
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Define the exact clean block scripts
    clean_scripts = """{% block scripts %}
<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
<script>
    function dashboardData() {
        return {
            rates: {{ rates | tojson }},
            products: {{ products_json | safe }},
            calc: { usd: 1, bs: ({{ rates.usd_oficial }}).toFixed(2) },
            vehicleModel: '',
            quoteReq: {
                oilId: '',
                oilPrice: 0,
                filterId: '',
                filterPrice: 0,
                oilQty: 4,
                includeLabor: true,
                includeLogistics: true
            },
            quoteRes: {
                total_usd: 0,
                total_bs: 0,
                total_cash_usd: 0
            },

            updateBs() {
                if (typeof this.calc.usd !== 'number') return;
                this.calc.bs = (this.calc.usd * this.rates.usd_oficial).toFixed(2);
            },
            updateUsd() {
                if (typeof this.calc.bs !== 'number') return;
                this.calc.usd = (this.calc.bs / this.rates.usd_oficial).toFixed(2);
            },
            shareQuote() {
                const date = new Date().toLocaleDateString('es-VE');
                const vehicle = this.vehicleModel || 'Vehículo';
                const totalBsFormatted = this.quoteRes.total_bs.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                const totalCashFormatted = this.quoteRes.total_cash_usd.toFixed(2);

                const text = `LubMovil - Presupuesto Rápido
Servicio para: ${vehicle}
---------------------------
💳 Pago Móvil / Digital: ${totalBsFormatted} Bs.
💵 Pago Efectivo USD: $${totalCashFormatted} (Precio con descuento)
---------------------------
Tasa BCV: ${this.rates.usd_oficial.toFixed(2)} Bs.`;
                window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
            },
            shareRate() {
                const date = new Date().toLocaleDateString('es-VE');
                const text = `Tasa LubMovil (${date}): ${this.rates.usd_oficial.toFixed(2)} Bs.`;
                window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
            },
            updateQuote() {
                let total = 0;
                if (this.quoteReq.oilId) total += (this.quoteReq.oilPrice * this.quoteReq.oilQty);
                if (this.quoteReq.filterId) total += this.quoteReq.filterPrice;
                if (this.quoteReq.includeLabor) total += 15.0;
                if (this.quoteReq.includeLogistics) total += 1.50;

                this.quoteRes.total_usd = total;
                this.quoteRes.total_bs = total * this.rates.usd_oficial;

                // Lógica de Precio Dual: Incentivo por Efectivo
                if (this.rates.cash_rate > 0) {
                    this.quoteRes.total_cash_usd = this.quoteRes.total_bs / this.rates.cash_rate;
                } else {
                    this.quoteRes.total_cash_usd = total;
                }
            },
            init() {
                this.updateQuote();
            }
        };
    }
</script>
{% endblock %}"""

    # Use regex to find and replace everything from {% block scripts %} to {% endblock %}
    pattern = re.compile(r'{% block scripts %}.*?{% endblock %}', re.DOTALL)
    new_content = pattern.sub(clean_scripts, content)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully fixed script block and indentation.")

if __name__ == "__main__":
    final_scripts_fix()

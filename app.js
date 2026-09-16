const width = window.innerWidth;
const height = window.innerHeight * 0.9;

const svg = d3
  .select("#map")
  .append("svg")
  .attr("width", width)
  .attr("height", height)
  .attr("viewBox", `0 0 ${width} ${height}`);

const tooltip = d3.select("#tooltip");

const colors = {
  green: "#4ade80",
  yellow: "#facc15",
  orange: "#fb923c",
  red: "#ef4444"
};

Promise.all([
  d3.json("data/departements.geojson"),
  d3.dsv(";", "data/prefets_departements.csv")
]).then(([geoData, prefets]) => {

  const prefetsMap = {};

  prefets.forEach(d => {
    prefetsMap[d.departement] = d;
  });

  const projection = d3.geoMercator()
    .fitSize([width, height], geoData);

  const path = d3.geoPath().projection(projection);

  svg.selectAll("path")
    .data(geoData.features)
    .enter()
    .append("path")
    .attr("class", "department")
    .attr("d", path)

    .attr("fill", d => {

      const code = d.properties.code;
      const prefet = prefetsMap[code];

      if (!prefet) return "#ccc";

      return colors[prefet.couleur_carte];
    })

    .on("mousemove", (event, d) => {

      const code = d.properties.code;
      const prefet = prefetsMap[code];

      if (!prefet) return;

      tooltip
        .style("opacity", 1)
        .html(`
          <strong>${prefet.territoire}</strong><br><br>

          ${prefet.nom_prefet}<br><br>

          ${prefet.titre_global}<br><br>

          En poste depuis :
          ${prefet.date_prise_fonction}<br>

          Ancienneté :
          ${prefet.anciennete_jours} jours
        `)

        .style("left", event.pageX + 20 + "px")
        .style("top", event.pageY + "px");
    })

    .on("mouseleave", () => {
      tooltip.style("opacity", 0);
    });

});
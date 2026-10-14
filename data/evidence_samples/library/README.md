# Photo library for the image-evidence test set

Real photos (Pexels licence, CC) plus one generated image, re-encoded without their original
metadata. Sources and licences: `SOURCES.json`. A case never uses these files directly: the stamping
script (`scripts/stamp_case_photos.py`) copies a library photo into `data/evidence_samples/cases/<case>/`
and writes the capture time, GPS position and software tag the case specifies.

What each photo shows (checked by a person, not by the model under test):

| file | shows |
|---|---|
| muddy_sneakers_in_car.jpg | A passenger's feet in sneakers caked with mud and clay on a car floor mat; mud on the mat |
| muddy_boots_in_car.jpg | Same kind of scene: muddy shoes on a car floor, mud on the mat |
| carpet_dirt_vacuum.jpg | A car's floor carpet visibly dirty (dust, debris, stains) while a gloved hand vacuums it |
| seat_clean_fabric_cleaning.jpg | A grey fabric car seat being cleaned with an extractor nozzle; the seat shows some faint marks |
| fastfood_bag_in_car.jpg | A paper fast-food bag sitting in a car; no spill visible |
| seat_clean_interior.jpg | A clean, modern car interior (front and rear seats), no mess |
| seat_clean_leather.jpg | Clean white leather front seat seen through the open door, no mess |
| seat_clean_white_leather.jpg | Clean white leather rear seats, no mess |
| mat_clean.jpg | A clean black rubber floor mat in a car footwell |
| coffee_spill_table.jpg | Coffee spilled on a white table next to a cup (not a car) |
| coffee_spill_steps.jpg | Two paper coffee cups spilled on stone steps outdoors (not a car) |
| wine_spill_floor.jpg | A tipped wine glass and spilled wine on a dark floor (not a car) |
| wrecked_car_exterior.jpg | The outside of a wrecked, crushed car in a scrapyard |
| ai_generated_seat.jpg | An AI-generated image of an empty grey car seat, no stain, with a "pollinations.ai" watermark |

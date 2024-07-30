from urllib import response
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models.functions import TruncMonth, Trunc
from django.db.models import Sum, Count, Q, DateField
from django.utils.timezone import now
from django.conf import settings
from django.utils.dateparse import parse_date
from django.db import transaction
from threading import Thread
from .models import Leads
from .forms import LeadsForm, CompanyForm
from .scripts.extract_companies import read_csv_data, main_extraction
from .scripts.traitement_text import *
from pulls.utils import login_required_connect
from elasticsearch import Elasticsearch, NotFoundError, RequestError, ConnectionError
from datetime import datetime, timedelta
from django.db.models.functions import TruncDate
from .models import Feedback
import csv
import re
import schedule
import time
import json
import pandas as pd
import matplotlib.pyplot as plt
import mpld3
import io
import base64
import urllib
import MySQLdb
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go
from django.db.models.functions import TruncMonth
from django.test import RequestFactory
from django.views.decorators.http import require_http_methods
import schedule
import time
from datetime import datetime, timedelta
from django.core.cache import cache
from decouple import config
import os
from pathlib import Path
from django.db import transaction
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor



def check_name(request):
    nom = request.GET.get('nom', '')
    exists = Leads.objects.filter(nom__iexact=nom).exists()
    return JsonResponse({'exists': exists})

def check_offer_name(request):
    nom_offre = request.GET.get('nom_offre', '')
    exists = Leads.objects.filter(nom_offre__iexact=nom_offre).exists()
    return JsonResponse({'exists': exists})


def check_offer_date(request):
    date_publication_offre = request.GET.get('date_publication_offre', '')
    date = parse_date(date_publication_offre)
    exists = Leads.objects.filter(date_publication_offre=date).exists()
    return JsonResponse({'exists': exists})

@login_required_connect
def add_company(request):
    return render(request, 'test/add_company.html')


@require_http_methods(["POST"])  
@csrf_protect  
def submit_form(request):
    if request.method == 'POST':
        data = request.POST

        # Extraire les données du formulaire
        nom = data.get('nom')
        nom_offre = data.get('nom_offre')
        date_publication_offre = parse_date(data.get('date_publication_offre'))

        # Utiliser update_or_create pour créer ou mettre à jour le lead
        lead, created = Leads.objects.update_or_create(
            nom=nom,
            nom_offre=nom_offre,
            date_publication_offre=date_publication_offre,
            defaults={
                'nombre_offres': data.get('nombre_offres',1),
                'localisation_du_lead': data.get('localisation',None),
                'porteur_lead': data.get('porteur_lead'),
                'url_profil_porteur_lead': data.get('url_profil_porteur_lead',None),
                'adresse_mail_de_contact': data.get('email',None),
                'telephone': data.get('telephone',None),
                'secteur_activite': data.get('secteur',None),
                'taille_entreprise': data.get('taille',None),
                'chiffre_d_affaires': data.get('chiffre_d_affaires',None),
                'source_lead': data.get('source_lead',None),
                'statut_du_lead': data.get('statut_du_lead',None ),
                'date_maj_lead': parse_date(data.get('date_maj_lead',None)),
                'remarques': data.get('remarques',None),
                'priorite': data.get('priorite',None),
                'description_job': data.get('description_job',None),
                'lien_vers_lead': data.get('lien_vers_lead',None)
            }
        )

        return JsonResponse({'success': True, 'created': created})
    return JsonResponse({'success': False}, status=400)


@login_required_connect
def visualisation_leads(request):
    user = request.user
    context = recup_infos_users(user)
    entreprises = Leads.objects.values_list('nom', flat=True).distinct()
    entreprise_selectionnee = request.GET.get('entreprise')
    search_query = request.GET.get('search', '')

    leads = Leads.objects.all()
    
    if entreprise_selectionnee:
        leads = leads.filter(nom=entreprise_selectionnee)
    
    if search_query:
        leads = leads.filter(
            Q(nom__icontains=search_query) |
            Q(nom_offre__icontains=search_query) |
            Q(localisation_du_lead__icontains=search_query)
        )

    context.update({
        'entreprises': entreprises,
        'entreprise_selectionnee': entreprise_selectionnee,
        'leads': leads,
        'search_query': search_query,
    })
    return render(request, 'test/apps-ecommerce-orders.html', context)


@login_required_connect
def statistiques_leads(request):
    user = request.user
    context = recup_infos_users(user)
    entreprise_selectionnee = request.GET.get('entreprise')
    offres = []
    charts = []

    if entreprise_selectionnee:
        offres = Leads.objects.filter(nom=entreprise_selectionnee).values('localisation_du_lead').annotate(total_offres=Sum('nombre_offres'))

        # 1. Camembert des offres par localisation
        locations = [offre['localisation_du_lead'] for offre in offres]
        counts = [offre['total_offres'] for offre in offres]
        fig = px.pie(values=counts, names=locations, title='Offres par localisation')
        charts.append(fig.to_html(full_html=False))

        # 2. Bar chart des offres par localisation
        fig = px.bar(x=locations, y=counts, labels={'x': 'Localisation', 'y': 'Nombre d\'offres'}, title='Nombre d\'offres par localisation')
        charts.append(fig.to_html(full_html=False))

    # 3. Bar chart des offres par entreprise (général)
    entreprises_offres = Leads.objects.values('nom').annotate(total_offres=Sum('nombre_offres')).order_by('-total_offres')
    entreprises = [offre['nom'] for offre in entreprises_offres]
    counts = [offre['total_offres'] for offre in entreprises_offres]
    fig = px.bar(x=entreprises, y=counts, labels={'x': 'Entreprise', 'y': 'Nombre d\'offres'}, title='Nombre d\'offres par entreprise')
    charts.append(fig.to_html(full_html=False))

    # 4. Pie chart des leads par statut (général)
    statuts_leads = Leads.objects.values('statut_du_lead').annotate(total_leads=Count('id'))
    statuts = [statut['statut_du_lead'] for statut in statuts_leads]
    counts = [statut['total_leads'] for statut in statuts_leads]
    fig = px.pie(values=counts, names=statuts, title='Répartition des leads par statut')
    charts.append(fig.to_html(full_html=False))

    # 5. Bar chart des priorités de leads (général)
    priorites_leads = Leads.objects.values('priorite').annotate(total_leads=Count('id'))
    priorites = [priorite['priorite'] for priorite in priorites_leads]
    counts = [priorite['total_leads'] for priorite in priorites_leads]
    fig = px.bar(x=priorites, y=counts, labels={'x': 'Priorité', 'y': 'Nombre de leads'}, title='Répartition des leads par priorité')
    charts.append(fig.to_html(full_html=False))

    # 6. Bar chart des leads par secteur d'activité
    secteurs_leads = Leads.objects.values('secteur_activite').annotate(total_leads=Count('id')).order_by('-total_leads')
    secteurs = [secteur['secteur_activite'] for secteur in secteurs_leads]
    counts = [secteur['total_leads'] for secteur in secteurs_leads]
    fig = px.bar(x=secteurs, y=counts, labels={'x': 'Secteur d\'activité', 'y': 'Nombre de leads'}, title='Nombre de leads par secteur d\'activité')
    charts.append(fig.to_html(full_html=False))

    # 7. Bar chart des leads par taille d'entreprise
    tailles_leads = Leads.objects.values('taille_entreprise').annotate(total_leads=Count('id')).order_by('-total_leads')
    tailles = [taille['taille_entreprise'] for taille in tailles_leads]
    counts = [taille['total_leads'] for taille in tailles_leads]
    fig = px.bar(x=tailles, y=counts, labels={'x': 'Taille d\'entreprise', 'y': 'Nombre de leads'}, title='Nombre de leads par taille d\'entreprise')
    charts.append(fig.to_html(full_html=False))

    # 8. Pie chart des leads par source
    sources_leads = Leads.objects.values('source_lead').annotate(total_leads=Count('id')).order_by('-total_leads')
    sources = [source['source_lead'] for source in sources_leads]
    counts = [source['total_leads'] for source in sources_leads]
    fig = px.pie(values=counts, names=sources, title='Répartition des leads par source')
    charts.append(fig.to_html(full_html=False))

    # # 9. Line chart des leads par mois
    # leads_par_mois = Leads.objects.annotate(month=TruncMonth('date_publication_offre')).values('month').annotate(total_leads=Count('id')).order_by('month')
    # months = [lead['month'].strftime('%Y-%m') for lead in leads_par_mois if lead['month'] is not None]
    # counts = [lead['total_leads'] for lead in leads_par_mois if lead['month'] is not None]
    # fig = px.line(x=months, y=counts, labels={'x': 'Mois', 'y': 'Nombre de leads'}, title='Nombre de leads par mois')
    # charts.append(fig.to_html(full_html=False))

    context.update({
        'entreprise_selectionnee': entreprise_selectionnee,
        'offres': offres,
        'charts': charts,
    })
    return render(request, 'test/statistiquesLeads.html', context)

def get_graph(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    string = base64.b64encode(buf.read())
    uri = urllib.parse.quote(string)
    return uri

#################################################################


@csrf_protect
@login_required_connect
def update_lead_view(request, id):
    lead = get_object_or_404(Leads, id=id)
    if request.method == 'POST':
        form = LeadsForm(request.POST, instance=lead)
        if form.is_valid():
            form.save()
            return redirect('view_leads')
    else:
        form = LeadsForm(instance=lead)
    return render(request, 'test/update_lead.html', {'form': form, 'lead': lead})

def view_leads(request):
    leads = Leads.objects.all()
    updated_id = request.GET.get('updated_id')
    return render(request, 'test/leads.html', {'leads': leads, 'updated_id': updated_id})

#####################################


@require_http_methods(["POST"])
@csrf_protect
@login_required_connect
def update_lead(request):
    # Récupération des données depuis le formulaire
    nom_offre = request.POST.get('nom_offre')
    localisation = request.POST.get('localisation')
    nom = request.POST.get('nom')
    nombre_offres = request.POST.get('nombre_offres')
    email = request.POST.get('email')
    telephone = request.POST.get('telephone')
    taille = request.POST.get('taille')
    secteur = request.POST.get('secteur')
    chiffre_d_affaires = request.POST.get('chiffre_d_affaires')
    lien_site = request.POST.get('lien_site')

    path_to_csv = 'leap_data.csv'
    
    # Chargement du CSV dans un DataFrame
    df = pd.read_csv(path_to_csv, delimiter=';')
    
    # Création d'un masque pour identifier la ligne à mettre à jour
    mask = (df['nom_offre'] == nom_offre) & (df['nom_entreprise'] == nom)
    
    # Vérification si au moins une ligne correspond aux critères
    if mask.any():
        # Mise à jour des données du lead
        df.loc[mask, 'localisation'] = localisation
        df.loc[mask, 'nombre_offres'] = nombre_offres
        df.loc[mask, 'email'] = email
        df.loc[mask, 'telephone'] = telephone
        df.loc[mask, 'taille'] = taille
        df.loc[mask, 'secteur'] = secteur
        df.loc[mask, 'chiffre_d_affaires'] = chiffre_d_affaires
        df.loc[mask, 'lien_site'] = lien_site
        
        # Sauvegarde du DataFrame modifié dans le fichier CSV
        df.to_csv(path_to_csv, index=False, sep=';')
        return JsonResponse({"success": True, "message": "Lead mis à jour avec succès."})
    else:
        return JsonResponse({"success": False, "message": "Lead non trouvé pour mise à jour."})

############################################"
@login_required_connect
def display_leads_to_delete(request):
    leads = Leads.objects.all()
    return render(request, 'test/display_leads_to_delete.html', {'leads': leads})

###############################################"
@login_required_connect
def delete_lead(request):
    if request.method == 'POST':
        lead_id = request.POST.get('id')
        try:
            lead = Leads.objects.get(id=lead_id)
            lead.delete()
            return JsonResponse({'success': True})
        except Leads.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Lead not found'})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

#################################################################################################################

'''cette partie de code est dédiée à la génération de lead , notamment utilisation du multi-threading  , et le script présent dans le dossier script , que fait du scraping de plusieurs sources 
'''

from django.http import JsonResponse
from threading import Thread
from .scripts.extract_companies import read_csv_data,main_extraction
from.scripts.linkedIn import scraping_apec
import json

async def run_in_executor(func, *args):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, func, *args)


@require_http_methods(["POST"])
def start_scraping(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        source_lead = data.get('sourceLead')
        
        if not source_lead:
            return JsonResponse({'status': 'error', 'message': 'La source du lead est obligatoire.'}, status=400)

        if source_lead == 'apec':
            keywords = data.get('keywords')
            salary_min = data.get('salaryMin')
            salary_max = data.get('salaryMax')
            search_nom = data.get('searchNom')

            if not keywords or not salary_min or not salary_max or not search_nom:
                return JsonResponse({'status': 'error', 'message': 'Tous les champs sont obligatoires pour APEC.'}, status=400)

            base_url = 'https://www.apec.fr/candidat/recherche-emploi.html/emploi'
            location = search_nom
            new_data = scraping_apec(base_url, location, keywords, salary_min, salary_max)
        elif source_lead == 'linkedin':
            search_city = data.get('searchCity')
            select_region = data.get('selectRegion')
            keywords = data.get('keywords')
            time_frame = data.get('selectTimeFrame')

            if not search_city or not select_region or not keywords or not time_frame:
                return JsonResponse({'status': 'error', 'message': 'Tous les champs sont obligatoires pour LinkedIn.'}, status=400)

            location = f"{search_city}, {select_region}, France"
            lien ,new_data = main_extraction(keywords, location, time_frame)
        else:
            return JsonResponse({'status': 'error', 'message': 'Source du lead inconnue.'}, status=400)
        
        return JsonResponse({'status':'success' , 'data' : new_data} , safe=False )

    except Exception as e:
        print(f"Error in start_scraping: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def company_detail(request, lead_id):
    lead = get_object_or_404(Leads, pk=lead_id)
    return render(request, 'test/company_detail.html', {'lead': lead})
#######################################################################################################
@require_http_methods(["GET"])
def search_city(request):
    query = request.GET.get('q', '').lower()
    try:
        df = pd.read_csv('nom_communes.csv', delimiter=';')
        df['Nom (minuscules)'] = df['Nom (minuscules)'].str.lower()
        
        # Filtrer les villes dont le nom contient la query
        filtered_df = df[df['Nom (minuscules)'].str.contains(query)]
        response_data = filtered_df[['Nom (minuscules)', 'Région']].drop_duplicates().to_dict(orient='records')
        
        return JsonResponse(response_data, safe=False)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    ###################################################################

@login_required_connect
def scrapingPage(request):
    return render(request,'test/scraping.html')

@login_required_connect
def matching_cv_view(request):
    return render(request, 'test/matching_cv.html')

########################################################################
''' cette partie est dédié au processus de matching de cv avec le descriptif de mission 
la vue prend des cvs récupérés par le javascript ( les cvs rentrés seront mis dans une liste , js , 
le but est de les récupérer , créer les index , puis effectuer le traitement du texte , le parsing des
cvs puis le traitement des cvs et faire le matching par  la suite à l'aide de l'instance crée par 
elastic search , qui parcout dans ces index de cvs , pour trouver le cv le plus adéquat avec un système de scoring mis en place
avec la formule TF*IDF*lengthString '''


from .scripts.traitement_text import *
es = Elasticsearch(["http://localhost:9200"], timeout=60)

def print_index_content(index_name):
    try:
        es = Elasticsearch(["http://localhost:9200"], timeout=60)

        hits = response['hits']['hits']
        print(f"Index content for '{index_name}':")
        for hit in hits:
            print(f"ID: {hit['_id']}")
            print(f"Source: {hit['_source']}")
            print("------------")
    
    except Exception as e:
        print(f"Error: {e}")


from elasticsearch import Elasticsearch, NotFoundError, RequestError
import time


def determine_remark(percentage):
    if percentage >= 80:
        return "Ce CV correspond très bien à ce besoin"
    elif percentage >= 60:
        return "Ce CV correspond bien à ce besoin malgré quelques notions manquantes"
    elif percentage >= 40:
        return "Ce CV pourrait correspondre à un besoin similaire avec moins de contraintes"
    elif percentage >= 20:
        return "Ce CV correpond moins à ce besoin par rapport à d'autres"
    else:
        return "Ce CV ne correspond pas à ce besoin ."

@require_http_methods(["POST"])
@login_required_connect
def process_matching(request):
    try:
        mission_text = request.POST.get('mission_text')
        langue_text = request.POST.get('langue_text')
        entreprises_text = request.POST.get('entreprises_text')
        competences_text = request.POST.get('competences_text')
        poids_mission = int(request.POST.get('poids_mission'))
        poids_langue = int(request.POST.get('poids_langue'))
        poids_entreprises = int(request.POST.get('poids_entreprises'))
        poids_competences = int(request.POST.get('poids_competences'))
        cv_files = request.FILES.getlist('cv_files')

        if not any([mission_text, langue_text, entreprises_text, competences_text]):
            return JsonResponse({"error": "Veuillez remplir au moins un champ de recherche."}, status=400)

        if not cv_files:
            return JsonResponse({"error": "Veuillez uploader au moins un fichier de CV."}, status=400)

        try:
            es.delete_by_query(index='cvs', body={"query": {"match_all": {}}})
        except NotFoundError:
            pass

        try:
            es.indices.create(index='cvs')
        except RequestError as e:
            if e.error == 'resource_already_exists_exception':
                pass
            else:
                raise

        cv_texts = []
        for file in cv_files:
            cv_text = extract_text_from_pdf(file)
            preprocessed_cv_text = preprocess_text_mission(cv_text)
            cv_texts.append((file.name, preprocessed_cv_text))

        for cv_filename, cv_text in cv_texts:
            index_document("cvs", cv_filename, {"filename": cv_filename, "content": cv_text})

        max_attempts = 50
        attempt = 0
        results = []

        while attempt < max_attempts and not results:
            # Rechercher les correspondances
            matching_results = search_matching_cvs(
                mission_text, langue_text, entreprises_text, competences_text,
                poids_mission, poids_langue, poids_entreprises, poids_competences
            )
            results = [{"filename": result['_source']['filename'], "score": result['_score'], "content": result['_source']['content']} for result in matching_results]
            if not results:
                time.sleep(1)
                attempt += 1

        if not results:
            return JsonResponse({"error": "Aucune correspondance trouvée après plusieurs tentatives."}, status=404)

        score_max = max(result['score'] for result in results)
        for result in results:
            result['percentage'] = (result['score'] / score_max) * 100
            result['remark'] = determine_remark(result['percentage'])
            
            # Calculate keyword occurrences
            keyword_occurrences = calculate_keyword_occurrences(result['content'], mission_text, langue_text, entreprises_text, competences_text)
            result['keyword_occurrences'] = keyword_occurrences

        results = sorted(results, key=lambda x: x['score'], reverse=True)

        return JsonResponse({"results": results})
    
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def calculate_keyword_occurrences(cv_content, mission_text, langue_text, entreprises_text, competences_text):
    keywords = (mission_text + ' ' + langue_text + ' ' + entreprises_text + ' ' + competences_text).split()
    keyword_occurrences = {keyword: cv_content.lower().count(keyword.lower()) for keyword in keywords}
    return keyword_occurrences



@login_required_connect
def upload_cv(request):
    if request.method == 'POST':
        try:
            file = request.FILES.get('cv_file')
            if not file:
                return JsonResponse({"error": "No file provided"}, status=400)

            # Extraire le texte du PDF et ajouter à l'index Elasticsearch
            cv_text = extract_text_from_pdf(file)
            preprocessed_cv_text = preprocess_text_cv(cv_text)

            es = Elasticsearch()
            doc = {
                'filename': file.name,
                'content': preprocessed_cv_text,
            }
            res = es.index(index='cvs', document=doc)
            
            return JsonResponse({"file_id": res['_id']})
        
        except Exception as e:
            print(f"Error: {e}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=400)

@login_required_connect
def delete_cv(request, cv_id):
    if request.method == 'DELETE':
        try:
            # Vérifier si le document existe
            res = es.get(index='cvs', id=cv_id, ignore=[404])
            if not res['found']:
                return JsonResponse({"error": "Document not found"}, status=404)
            
            # Supprimer le document de l'index Elasticsearch
            es.delete(index='cvs', id=cv_id)
            
            return JsonResponse({"message": "Document deleted successfully"})
        
        except Exception as e:
            print(f"Error: {e}")
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Invalid request method."}, status=400)
    
from django.core.paginator import Paginator
from .models import Leads

@login_required_connect
def search_results(request):
    query = request.GET.get('query', '')
    search_type = request.GET.get('type', 'offre')
    
    if search_type == 'offre':
        leads = Leads.objects.filter(nom_offre__icontains=query)
    else:
        leads = Leads.objects.filter(nom__icontains=query)
    
    paginator = Paginator(leads, 20)  # 20 leads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    leads_data = list(page_obj.object_list.values('id', 'nom_offre', 'nom', 'nombre_offres', 'localisation_du_lead','porteur_lead'))
    return JsonResponse({
        'leads': leads_data,
        'num_pages': paginator.num_pages,
        'current_page': page_obj.number,
    })


#############################################################################"

@login_required_connect
def changer_mots_cle_lead(request, lead_id):
    lead = get_object_or_404(Leads, pk=lead_id)
    processed_description = preprocess_text_mission(lead.description_job)
    full_description = f"{lead.nom_offre} {processed_description}"
    keywords = extract_keywords(full_description)
    print('La description est :', full_description)
    print(f'Les mots clés retournés sont : {keywords}')
    return render(request, 'test/changer_mots_cle_lead.html', {'lead': lead, 'keywords': keywords})

from django.db.models import Q

@login_required_connect
def template_choix_leads(request):
    entreprises = Leads.objects.values_list('nom', flat=True).distinct()
    entreprise_selectionnee = request.GET.get('entreprise', '')
    search_query = request.GET.get('search', '')
    filter_type = request.GET.get('filter', 'all')

    leads = Leads.objects.all()

    if filter_type == 'recent':
        leads = leads.order_by('-date_maj_lead')[:10]
    elif entreprise_selectionnee:
        leads = leads.filter(nom=entreprise_selectionnee)
    elif search_query:
        leads = leads.filter(
            Q(nom__icontains=search_query) |
            Q(nom_offre__icontains=search_query) |
            Q(localisation_du_lead__icontains=search_query)
        )

    context = {
        'entreprises': entreprises,
        'entreprise_selectionnee': entreprise_selectionnee,
        'leads': leads,
        'search_query': search_query,
    }
    return render(request, 'test/choix_job_matching.html', context)

##################################################""
#matching process v2 

@require_http_methods(["POST"])
@login_required_connect
def process_matching_v2(request):
    try:
        mission_text = request.POST.get('mission_text')
        keywords_text = request.POST.get('keywords_text')
        poids_lead = int(request.POST.get('poids_lead'))
        poids_keywords = int(request.POST.get('poids_keywords'))
        cv_files = request.FILES.getlist('cv_files')

        if not mission_text and not keywords_text:
            return JsonResponse({"error": "Veuillez remplir au moins un champ de recherche."}, status=400)

        if not cv_files:
            return JsonResponse({"error": "Veuillez uploader au moins un fichier de CV."}, status=400)

        try:
            es.delete_by_query(index='cvs', body={"query": {"match_all": {}}})
        except NotFoundError:
            pass

        try:
            es.indices.create(index='cvs')
        except RequestError as e:
            if e.error == 'resource_already_exists_exception':
                pass
            else:
                raise

        cv_texts = []
        for file in cv_files:
            cv_text = extract_text_from_pdf(file)
            preprocessed_cv_text = preprocess_text_mission(cv_text)
            cv_texts.append((file.name, preprocessed_cv_text))

        for cv_filename, cv_text in cv_texts:
            index_document("cvs", cv_filename, {"filename": cv_filename, "content": cv_text})

        max_attempts = 50
        attempt = 0
        results = []

        while attempt < max_attempts and not results:
            matching_results = search_matching_cvs_v2(
                mission_text, keywords_text,
                poids_lead, poids_keywords
            )
            results = [{"filename": result['_source']['filename'], "score": result['_score'], "content": result['_source']['content']} for result in matching_results]
            if not results:
                time.sleep(1)
                attempt += 1

        if not results:
            return JsonResponse({"error": "Aucune correspondance trouvée après plusieurs tentatives."}, status=404)

        score_max = max(result['score'] for result in results)
        for result in results:
            result['percentage'] = (result['score'] / score_max) * 100
            result['remark'] = determine_remark(result['percentage'])
            keyword_occurrences = calculate_keyword_occurrences_v2(result['content'], mission_text, keywords_text)
            result['keyword_occurrences'] = keyword_occurrences

        results = sorted(results, key=lambda x: x['score'], reverse=True)

        return JsonResponse({"results": results})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
from collections import Counter
def calculate_keyword_occurrences_v2(content, mission_text, keywords_text):
    keywords = keywords_text.split()
    keyword_counts = Counter()

    for keyword in keywords:
        count = len(re.findall(r'\b{}\b'.format(re.escape(keyword)), content, re.IGNORECASE))
        keyword_counts[keyword] += count

    return keyword_counts
    ##########################################################################

from django.db.models import DateField
from django.db.models.functions import Trunc
from django.utils import timezone

# def history(request):
#     global notification_triggered
#     Leads.objects.filter(date_maj_lead__isnull=True).update(date_maj_lead=timezone.now())
#     leads = Leads.objects.annotate(date=Trunc('date_maj_lead', 'day', output_field=DateField())).order_by('-date_maj_lead')
#     grouped_leads = {}
#     for lead in leads:
#         date = lead.date.strftime('%Y-%m-%d')
#         if date not in grouped_leads:
#             grouped_leads[date] = []
#         grouped_leads[date].append(lead)

#     context = {
#         'grouped_leads': grouped_leads,
#         'show_notification': notification_triggered  # Ajouter l'état de la notification au contexte
#     }
#     notification_triggered = False
#     # Reset notification state
#     notification_triggered = False
#     return render(request, 'test/historique.html', context)

from django.shortcuts import render
from django.utils.timezone import now
from .models import Leads
from django.db.models.functions import Trunc
from django.db.models import DateField

@login_required_connect
def manage_leads_view(request, template_name):
    global notification_triggered

    Leads.objects.filter(date_maj_lead__isnull=True).update(date_maj_lead=now())
    leads = Leads.objects.annotate(date=Trunc('date_maj_lead', 'day', output_field=DateField())).order_by('-date_maj_lead')
    grouped_leads = {}
    for lead in leads:
        date = lead.date.strftime('%Y-%m-%d')
        if date not in grouped_leads:
            grouped_leads[date] = []
        grouped_leads[date].append(lead)

    context = {
        'grouped_leads': grouped_leads,
        'show_notification': notification_triggered  # Ajouter l'état de la notification au contexte
    }

    # Reset notification state
    notification_triggered = False

    return render(request, template_name, context)

@login_required_connect
def history(request):
    return manage_leads_view(request, 'test/historique.html')

##############################""

def get_user_type(user_type):
    match user_type:
            case 'paie':
                return "Ressources humaines"
            case 'admin':
                return "Direction"
            case 'stt':
                return "Freelance"
            case 'con':
                return "Consultant"
            case 'com':
                return "Commercial"
            case 'sup':
                return "Super admin"
            case _:
                return "Invité"

@login_required_connect
def choix_leads(request):
    user = request.user
    users_types =  get_user_type(user.users_type)
    
    context = {'user' : user 
               }
    context['type']= users_types
   
    if context:
        return render(request , 'test/choix_leads.html',context)
    else : 
        return manage_leads_view(request, 'test/choix_leads.html' )
        

#####################################################"
'''cette partie de code est dédiée à la partie programmation des leads afin que à l'instar d'un principe 
d'une cron tab que la tache génération de leads se lance systématiquement sans intervention humaine '''

import threading

default_data = {
    'nom': 'Paris',
    'region': 'Île-de-France',
    'keywords': 'ingénieur cloud devops',
    'time_frame': 'dernières 24h'
}

@require_http_methods(["POST"])
@login_required_connect
def recup_donnees_programmees(request):
    if request.method == 'POST':
        data = request.POST
        # Mettez à jour les valeurs par défaut avec les nouvelles données
        global default_data
        default_data.update({
            'nom': data.get('nom', default_data['nom']),
            'region': data.get('region', default_data['region']),
            'keywords': data.get('keywords', default_data['keywords']),
            'time_frame': data.get('time_frame', default_data['time_frame']),
        })
        return JsonResponse({"status": "success", "data": default_data})
    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})

@login_required_connect
def programmation_view(request):
    message=f'la valeur de default data est {default_data}'
    context={'message':message,
             'default_data':default_data}
    return render(request, 'test/programmation_leads.html', context)


from django.test import RequestFactory
from django.urls import reverse
import json
from .views import recup_donnees_programmees, start_scraping

def simulate_request():
    try:
        print('La simulation de la tâche est en train de commencer')
        factory = RequestFactory()

        # Créez une requête POST pour récupérer les données programmées
        recup_donnees_url = reverse('recup_donnees_programmees')
        request = factory.post(recup_donnees_url, data={}, content_type='application/json')
        response = recup_donnees_programmees(request)

        if response.status_code == 200:
            updated_data = json.loads(response.content).get('data', default_data)
            print(f"Data utilisée pour le scraping: {updated_data}")

            # Utilisez les données mises à jour pour la requête de scraping
            start_scraping_url = reverse('start_scraping')
            scraping_request = factory.post(start_scraping_url, data=json.dumps(updated_data), content_type='application/json')
            scraping_response = start_scraping(scraping_request)

            # Affichez la réponse pour vérifier
            print(f"Réponse reçue: {scraping_response.content}")
        else:
            print("Erreur lors de la récupération des données mises à jour.")
    except Exception as e:
        print(f"Erreur dans simulate_request: {e}")



notification_triggered = False

def send_notification():
    global notification_triggered
    print("Sending notification to users")
    notification_triggered = True



def run_schedule():
    schedule.every(1000).minutes.do(simulate_request)
    last_run = datetime.now() - timedelta(minutes=1000)  # Initialiser pour permettre l'exécution immédiate

    while True:
        now = datetime.now()
        if now - last_run >= timedelta(minutes=1000):
            schedule.run_pending()  # Vérifie et exécute les tâches planifiées si leur heure est arrivée
            last_run = now  # Mettre à jour l'heure de la dernière exécution
            send_notification()  # Envoyer la notification après l'exécution de la tâche
        time.sleep(200)  # Pause de 30 secondes pour éviter une utilisation excessive du processeur

# Lancer la fonction de planification dans un thread séparé
def start_scheduler():
    print('dans start scheduler')
    scheduler_thread = threading.Thread(target=run_schedule)
    scheduler_thread.daemon = True  # Assure que le thread se termine lorsque le programme principal se termine
    scheduler_thread.start()


def lead_details(request):
    nom = request.GET.get('nom')
    nom_offre = request.GET.get('nom_offre')

    lead = get_object_or_404(Leads, nom=nom, nom_offre=nom_offre)
    return render(request, 'test/company_detail.html', {'lead': lead})

''' cette partie concerne la partie migration de la CV tech , on va faire un script afin de pouvoir
afficher les CVs post-migration de la CV-tech afin de respecter par la suite ce pattern '''
import MySQLdb

def get_cvs():
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )
    cursor = db.cursor()
    cursor.execute("SELECT c.id, c.name, c.store_fname, c.mimetype, c.create_uid, u.id as user_id, u.login as email_utilisateur, c.create_date, c.write_date, c.file_size, c.tjm, c.description FROM cv as c LEFT JOIN odoo_users as u ON c.create_uid = u.id;")
    cvs = cursor.fetchall()
    db.close()
    return cvs

@login_required_connect
def cv_detail(request, cv_id):
    actual_path = f"{os.getcwd()}/tests"
    CV_ROOT = "/media/CV/filestore/"

    cvs = get_cvs()
    cv = next((cv for cv in cvs if int(cv[0]) == cv_id), None)
    if cv is None:
        print(f'Le CV avec l\'ID {cv_id} n\'a pas été trouvé.')
        return render(request, 'test/choix_leads.html')  # Page 404 si le CV n'est pas trouvé

    cv_file_path = os.path.join(CV_ROOT, cv[2])
    proprietaire_cv = cv[6].split('@')[0]
    if '.' in proprietaire_cv:
        nom = proprietaire_cv.split('.')[1]
        prenom = proprietaire_cv.split('.')[0]
    else:
        nom = proprietaire_cv
        prenom = proprietaire_cv

    nom_du_cv = cv[1]
    nom_cv = get_noms_cvs(nom_du_cv)

    liste_info = [nom, prenom, nom_cv]
    cv_file_path = Path(cv_file_path)
    cv_file_url = f'file:///{cv_file_path.as_posix()}'

    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )
    cursor = db.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM comments WHERE cv_id = %s ORDER BY created_at DESC", [cv_id])
    comments = cursor.fetchall()
    db.close()

    return render(request, 'test/cv_detail.html', {'cv': cv, 'cv_file_url': cv_file_url, 'proprietaire': liste_info, 'comments': comments})


def update_cv(request):
    if request.method == 'POST':
        try:
            cv_id = request.POST.get('cv_id')
            field = request.POST.get('field')
            value = request.POST.get('value')

            db = MySQLdb.connect(
                host=config('DB_HOST'),
                user=config('DB_USER'),
                passwd=config('DB_PASSWORD'),
                db=config('DB_NAME'),
                port=3306
            )
            cursor = db.cursor()

            if field in ['tjm', 'description']:
                query = f"UPDATE cv SET {field} = %s WHERE id = %s"
                cursor.execute(query, [value, cv_id])
                db.commit()
                db.close()
                return JsonResponse({'success': True})

            db.close()
            return JsonResponse({'success': False, 'error': 'Invalid field'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    


def recuperer_cvs():
    # Configuration de la connexion à la base de données Odoo
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )

    # Vérifier si les données sont en cache
    cached_data = cache.get('all_cvs_data')
    if cached_data:
        return cached_data['cvs'], cached_data['columns']

    # Créer un curseur pour exécuter les requêtes SQL
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.store_fname, c.mimetype, c.create_uid, c.file_size, c.create_date, c.write_date, u.login as email_utilisateur 
        FROM cv AS c 
        LEFT JOIN odoo_users AS u ON c.create_uid = u.id limit 100
    """)

    # Récupérer les résultats de la requête
    cvs = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    print('La récupération des Cvs s\'est correctement effectuée')

    # Fermer la connexion à la base de données
    db.close()

    # Mettre en cache les données pour une durée déterminée
    cache.set('all_cvs_data', {'cvs': cvs, 'columns': columns}, timeout=3600)  # Cache pour 3600 secondes

   

    # Retourner les résultats
    return cvs, columns


def recup_infos_users(user):
    users_types =  get_user_type(user.users_type)
    
    context = {'user' : user 
               }
    context['type']= users_types
    return context


@login_required_connect
def cv_interface(request):
    user = request.user
    context = recup_infos_users(user)

    try:
        # Récupération des CVs depuis la base de données
        cvs, columns = recuperer_cvs()
        cv_list = []
        for cv in cvs:
            cv_data = dict(zip(columns, cv))
            if cv_data['id'] is None:
                continue

            proprietaire_cv = cv_data.get('email_utilisateur', 'inconnu')
            if proprietaire_cv and '@' in proprietaire_cv:
                proprietaire_cv = proprietaire_cv.split('@')[0]
                nom, prenom = proprietaire_cv.split('.') if '.' in proprietaire_cv else (proprietaire_cv, proprietaire_cv)
            else:
                nom = 'inconnu'
                prenom = 'inconnu'

            create_date = cv_data['create_date'].strftime('%Y-%m-%d %H:%M:%S') if cv_data['create_date'] else None
            write_date = cv_data['write_date'].strftime('%Y-%m-%d %H:%M:%S') if cv_data['write_date'] else None

            cv_list.append({
                'id': cv_data['id'],
                'name': cv_data['name'],
                'store_fname': cv_data['store_fname'],
                'mimetype': cv_data['mimetype'],
                'cv_proprio': cv_data['create_uid'],
                'email_utilisateur': cv_data['email_utilisateur'],
                'file_size': cv_data['file_size'],
                'nom': nom,
                'prenom': prenom,
                'create_date': create_date,
                'write_date': write_date
            })

        context['cvs'] = cv_list

    except Exception as e:
        print(f"An error occurred: {e}")

    return render(request, 'pages/settings/files_manager.html', context)


def get_noms_cvs(nom_cv):
    # Configuration de la connexion à la base de données Odoo
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )

    # Créer un curseur pour exécuter les requêtes SQL
    cursor = db.cursor()

    # Exécuter la requête SQL pour récupérer les données de la table cv
    query = f'''
    SELECT nom_propre.nom_propre
    FROM cv AS c
    LEFT JOIN nom_propre ON nom_propre.filename = %s
    WHERE nom_propre.nom_propre IN (SELECT nom_propre FROM nom_propre)
    '''
    cursor.execute(query, (nom_cv,))

    # Récupérer les résultats de la requête
    cvs = cursor.fetchone()
    print('La récupération des CVs s\'est correctement effectuée')

    # Fermer la connexion à la base de données
    db.close()

    # Retourner les résultats
    return cvs[0]


 
def update_cv_fields(request, cv_id):
    if request.method == 'POST':
        tjm = request.POST.get('tjm')
        description = request.POST.get('description')

        try:
            # Connexion à la base de données
            db = MySQLdb.connect(
                host=config('DB_HOST'),
                user=config('DB_USER'),
                passwd=config('DB_PASSWORD'),
                db=config('DB_NAME'),
                port=3306
            )
            cursor = db.cursor()
            if tjm is not None:
                cursor.execute("UPDATE cv SET tjm = %s WHERE id = %s", (tjm, cv_id))
            if description is not None:
                cursor.execute("UPDATE cv SET description = %s WHERE id = %s", (description, cv_id))
            db.commit()
            db.close()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def get_facs():
    # Configuration de la connexion à la base de données Odoo
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )

    # Créer un curseur pour exécuter les requêtes SQL
    cursor = db.cursor()

    # Exécuter la requête SQL pour récupérer les données de la table cv
    cursor.execute("SELECT c.id, c.name, c.store_fname , c.mimetype , c.create_uid as cv_proprio, u.id as user_id, u.login as email_utilisateur from facture as c left join odoo_users as u on c.create_uid = u.id ;")

    # Récupérer les résultats de la requête
    cvs = cursor.fetchall()
    print('la récupération des factures s\'est correctement effectuée ')
    # Fermer la connexion à la base de données
    db.close()

    # Retourner les résultats
    return cvs

def fac_detail(request, fac_id):
    actual_path= f"{os.getcwd()}/tests"
    CV_ROOT = "/media/CV/filestore/"
    facs = get_facs()
    fac = next((fac for fac in facs if int(fac[0]) == fac_id), None)
    if fac is None:
        print(f'le cv avec l\'id {fac_id} n\'a pas été trouvé ')
        return render(request, 'test/choix_leads.html')  # Page 404 si le CV n'est pas trouvé

    # Générer l'URL du fichier CV
    fac_file_path = os.path.join(CV_ROOT, fac[2])
    proprietaire_fac = fac[6].split('@')[0]
    if '.' in proprietaire_fac:
        nom = proprietaire_fac.split('.')[1]
        prenom = proprietaire_fac.split('.')[0]
    else:
        nom = proprietaire_fac
        prenom = proprietaire_fac
    
    nom_fac =  fac[1]
    
    
    liste_info = [nom ,prenom,nom_fac]
    # fac_file_url = f'file:///{fac_file_path.replace("\\", "/")}'
    fac_file_path = Path(fac_file_path)
    fac_file_url = 'file:///{0}'.format(fac_file_path.as_posix())
    return render(request, 'test/fac_detail.html', {'fac': fac, 'cv_file_url': fac_file_url ,'proprietaire' : liste_info})
    

##################################################################################################################"""""
''' cette partie du code est dédiée à l'automatisation du scraping'''


def get_cvs_condition(nombre_cvs):
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )

    # Créer un curseur pour exécuter les requêtes SQL
    
    cursor = db.cursor()

        # Exécuter la requête SQL pour récupérer les données de la table cv
    query = f"SELECT id, name, store_fname FROM cv WHERE mimetype = 'application/pdf' order by create_date desc LIMIT {nombre_cvs};"
    cursor.execute(query)

        # Récupérer les résultats de la requête
    cvs = cursor.fetchall()
    print('La récupération des CVs s\'est correctement effectuée.')

        # Fermer la connexion à la base de données
    db.close()

    # Retourner les résultats
    return cvs


def find_first_match(text):
    # regex pour le numéro de téléphone
    text1 = text.replace(" ", "").replace("-", "").replace(".","").replace("_","")
    phone_pattern = r"(?<!#)(0\d{9}|\+33\d{9})"
    # Regex pattern to match an email address
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(com|fr)"

    phone_match = re.search(phone_pattern, text1)
    email_match = re.search(email_pattern, text)

    phone_result = phone_match.group() if phone_match else None
    email_result = email_match.group() if email_match else None

    return phone_result, email_result


def recuperer_num_mail(cv_id):
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )

    # Créer un curseur pour exécuter les requêtes SQL
    cursor = db.cursor()
    query = f"SELECT index_content FROM cv WHERE id = {cv_id};"
    cursor.execute(query)
    reponse = cursor.fetchone()
    if reponse:
        phone, email = find_first_match(str(reponse))
        return phone, email
    return None, None

def get_commentaires(request, cv_id):
    # Connexion à la base de données
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )
    cursor = db.cursor(MySQLdb.cursors.DictCursor)

    try:
        # Récupération des commentaires associés au CV
        cursor.execute("SELECT * FROM comments WHERE cv_id = %s ORDER BY created_at DESC", [cv_id])
        comments = cursor.fetchall()

    finally:
        db.close()

    return JsonResponse({'comments': comments})

@require_http_methods(["POST"])
def process_matching_v3(request):
    try:
        actual_path = f"{os.getcwd()}/tests"
        CV_ROOT = "/media/CV/filestore/"
        mission_text = request.POST.get('mission_text')
        keywords_text = request.POST.get('keywords_text')
        poids_lead = request.POST.get('poids_lead')
        poids_keywords = request.POST.get('poids_keywords')
        number_of_cvs = request.POST.get('number_of_cvs', 100)

        print('number_of_cvs recuperer:', mission_text)

        if poids_lead is not None:
            poids_lead = int(poids_lead)
            print('poids_leads:', poids_lead)
        else:
            poids_lead = 0
            print('poids_leads non recuperer:', poids_lead)

        if poids_keywords is not None:
            poids_keywords = int(poids_keywords)
            print('poids_keywords:', poids_keywords)
        else:
            poids_keywords = 0
            print('poids_keywords non recuperer:', poids_keywords)

        number_of_cvs = int(number_of_cvs)
        print('number_of_cvs non recuperer:', number_of_cvs)

        if not mission_text and not keywords_text:
            return JsonResponse({"error": "Veuillez remplir au moins un champ de recherche."}, status=400)

        # Fetch CVs from the database
        print("Fetching CVs from database")
        cvs = get_cvs_condition(nombre_cvs=number_of_cvs)
        print("CVs fetched:", cvs)

        if not cvs:
            return JsonResponse({"error": "Aucun CV trouvé dans la base de données."}, status=400)

        try:
            es.delete_by_query(index='cvs', body={"query": {"match_all": {}}})
        except NotFoundError:
            print("Index not found, no need to delete.")
        except Exception as e:
            print(f"Error deleting index: {str(e)}")

        try:
            es.indices.create(index='cvs')
        except RequestError as e:
            if e.error == 'resource_already_exists_exception':
                print("Index already exists, no need to create.")
            else:
                print(f"RequestError: {str(e)}")
                raise
        except ConnectionError as ce:
            print(f"ConnectionError: {str(ce)}")
            return JsonResponse({"error": f"Erreur de connexion à Elasticsearch : {str(ce)}"}, status=500)

        cv_texts = []
        for cv in cvs:
            cv_file_path = os.path.join(settings.CV_ROOT, cv[2] + ".pdf")
            if not os.path.isfile(cv_file_path):
                print(f"File not found: {cv_file_path}")
                continue
            else:
                print(f"ok pour le cv {cv_file_path}")
            try:
                cv_text = extract_text_from_pdf_path(cv_file_path)
            except Exception as e:
                print(f"Error extracting text from {cv_file_path}: {str(e)}")
                continue
            preprocessed_cv_text = preprocess_text_mission(cv_text)
            cv_texts.append((cv[0], cv[1], preprocessed_cv_text))

        for cv_id, cv_filename, cv_text in cv_texts:
            print(f"Indexing CV: {cv_id}, {cv_filename}")
            try:
                index_document("cvs", cv_id, {"filename": cv_filename, "content": cv_text})
            except Exception as e:
                print(f"Error indexing document {cv_id}: {str(e)}")

        print('Indexation réussie')

        max_attempts = 50
        attempt = 0
        results = []

        while attempt < max_attempts and not results:
            try:
                matching_results = search_matching_cvs_v2(
                    mission_text, keywords_text,
                    poids_lead, poids_keywords
                )
                results = [{"id": result['_id'], "filename": result['_source']['filename'], "score": result['_score'], "content": result['_source']['content']} for result in matching_results]
            except ConnectionError as ce:
                print(f"ConnectionError during search: {str(ce)}")
                return JsonResponse({"error": f"Erreur de connexion à Elasticsearch : {str(ce)}"}, status=500)
            except Exception as e:
                print(f"Error during search: {str(e)}")

            if not results:
                time.sleep(1)
                attempt += 1

        if not results:
            return JsonResponse({"error": "Aucune correspondance trouvée après plusieurs tentatives."}, status=404)

        score_max = max(result['score'] for result in results)
        for result in results:
            result['percentage'] = (result['score'] / score_max) * 100
            result['remark'] = determine_remark(result['percentage'])
            keyword_occurrences = calculate_keyword_occurrences_v2(result['content'], mission_text, keywords_text)
            result['keyword_occurrences'] = keyword_occurrences

            # Fetch phone and email
            phone, email = recuperer_num_mail(result['id'])
            result['phone'] = phone
            result['email'] = email

        results = sorted(results, key=lambda x: x['score'], reverse=True)

        return JsonResponse({"results": results})

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

# récuperation des commentaires de la table des cvs
def recuperer_commentaires(cv_id):
  

    # Configuration de la connexion à la base de données
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )

    # Vérifier si les commentaires sont en cache
    cache_key = f'comments_data_{cv_id}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    # Créer un curseur pour exécuter les requêtes SQL
    cursor = db.cursor()

    # Exécuter la requête SQL pour récupérer les commentaires de la table comments
    cursor.execute("SELECT c.id, c.cv_id, c.user_id, c.comment, c.created_at, u.username FROM comments AS c LEFT JOIN auth_user AS u ON c.user_id = u.id WHERE c.cv_id = %s ORDER BY c.created_at DESC;", (cv_id,))

    # Récupérer les résultats de la requête
    comments = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    print('La récupération des commentaires s\'est correctement effectuée')

    # Fermer la connexion à la base de données
    db.close()

    # Mettre en cache les données pour une durée déterminée
    cache.set(cache_key, {'comments': comments, 'columns': columns}, timeout=3600)  # Cache pour 3600 secondes (1 heure)

    # Retourner les résultats
    return {'comments': comments, 'columns': columns}



import logging

# Configurez le logger
logger = logging.getLogger(__name__)
@login_required_connect
def add_comment(request):
    if request.method == 'POST':
        cv_id = request.POST.get('cv_id')
        comment = request.POST.get('comment')
        user = request.user
        user_name = user.users_fname
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        status = 'nouveau'

        logger.info(f'Received data: cv_id={cv_id}, comment={comment}, user_name={user_name}')

        if cv_id and comment:
            try:
                db = MySQLdb.connect(
                    host=config('DB_HOST'),
                    user=config('DB_USER'),
                    passwd=config('DB_PASSWORD'),
                    db=config('DB_NAME'),
                    port=3306
                )
                cursor = db.cursor()
                cursor.execute(
                    "INSERT INTO comments (cv_id, user_name, comment, created_at, status) VALUES (%s, %s, %s, %s, %s)", 
                    (cv_id, user_name, comment, current_date, status)
                )
                db.commit()
                db.close()
                logger.info('Commentaire ajouté avec succès')
                return JsonResponse({'message': 'Commentaire ajouté avec succès', 'user_name': user_name, 'comment': comment, 'created_at': current_date})
            except MySQLdb.Error as e:
                logger.error(f"Erreur MySQLdb: {e}")
                return JsonResponse({'error': 'Erreur lors de l\'ajout du commentaire'}, status=500)
        else:
            logger.warning('Données invalides: cv_id ou comment manquant')
            print(cv_id , comment)
            return JsonResponse({'error': 'Données invalides'}, status=400)
    else:
        logger.error('Méthode non autorisée')
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

from django.views.decorators.http import require_POST


@require_POST
def update_comment_status(request):
    comment_id = request.POST.get('comment_id')
    new_status = request.POST.get('status')

    if not comment_id or not new_status:
        return JsonResponse({'error': 'Invalid data'}, status=400)

    try:
        db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
        )
        cursor = db.cursor()
        cursor.execute(
            "UPDATE comments SET status = %s WHERE id = %s", 
            (new_status, comment_id)
        )
        db.commit()
        db.close()
        return JsonResponse({'message': 'Status updated successfully'})
    except MySQLdb.Error as e:
        return JsonResponse({'error': str(e)}, status=500)
    
@login_required_connect
def historique_commentaires(request, cv_id):
    # Connexion à la base de données
    context = {}
    db = MySQLdb.connect(
        host=config('DB_HOST'),
        user=config('DB_USER'),
        passwd=config('DB_PASSWORD'),
        db=config('DB_NAME'),
        port=3306
    )
    cursor = db.cursor(MySQLdb.cursors.DictCursor)

    try:
        # Récupération des commentaires associés au CV
        cursor.execute("SELECT * FROM comments WHERE cv_id = %s ORDER BY created_at DESC", [cv_id])
        comments = cursor.fetchall()

        # Récupération du nom du CV
        cursor.execute("SELECT name FROM cv WHERE id = %s", [cv_id])
        cv_name = cursor.fetchone()

    finally:
        db.close()

    context['comments'] = comments
    context['cv_name'] = cv_name['name'] if cv_name else 'Nom du CV non trouvé'
    context['cv_id'] = cv_id

    # Si la requête est faite via AJAX, renvoyer seulement les commentaires en JSON
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'comments': comments, 'cv_name': context['cv_name'], 'cv_id': cv_id})

    return render(request, 'test/apps-projects-details.html', context)

def matching(request):
    return render(request , 'test/matching.html')


def get_leads_stats(request):
    stats = Leads.objects.annotate(date=TruncDate('date_publication_offre')).values('date', 'nom').annotate(total_leads=Count('id')).order_by('date')
    data = {
        'labels': list(set(stat['date'].strftime('%Y-%m-%d') for stat in stats)),
        'datasets': []
    }
    companies = list(set(stat['nom'] for stat in stats))
    for company in companies:
        company_data = {
            'label': company,
            'data': [stat['total_leads'] for stat in stats if stat['nom'] == company],
            'borderColor': '#' + ''.join([format(ord(char), 'x') for char in company][:6]),
            'fill': False
        }
        data['datasets'].append(company_data)
    
    return JsonResponse(data)




@login_required_connect
def feedback(request):
    user=request.user
    context = recup_infos_users(user)
    feedbacks = Feedback.objects.all().order_by('-created_at')
    context['feedbacks']=feedbacks
    pinned_feedbacks = Feedback.objects.filter(is_pinned=True, is_deleted=False).order_by('-created_at')
    context['pinned_feedbacks']=pinned_feedbacks
    return render(request, 'test/apps-chat.html', context)


@login_required_connect
def add_feedback(request):
    user = request.user 
    context=recup_infos_users(user)
    if request.method == 'POST':
        data = json.loads(request.body)
        comment = data.get('comment')
        if comment:
            feedback = Feedback.objects.create(
                user=user,
                comment=comment,
                created_at=timezone.now(),
                status='nouveau'
            )
            return JsonResponse({
                'user_name': request.user.users_name,
                'comment': feedback.comment,
                'created_at': feedback.created_at.strftime('%H:%M')
            })
        else:
            return JsonResponse({'error': 'Commentaire invalide'}, status=400)
    feedbacks = Feedback.objects.filter(is_deleted=False).order_by('-created_at')
    pinned_feedbacks = Feedback.objects.filter(is_pinned=True, is_deleted=False).order_by('-created_at')

    context['feedbacks']= feedbacks
    context['pinned_feedbacks']=pinned_feedbacks
    return render(request, 'test/apps-chat.html', context)


def pin_feedback(request, id):
    if request.method == 'POST':
        try:
            feedback = Feedback.objects.get(id=id)
            feedback.is_pinned = True
            feedback.save()
            return JsonResponse({'message': 'Commentaire épinglé avec succès!'}, status=200)
        except Feedback.DoesNotExist:
            return JsonResponse({'message': 'Commentaire non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'message': str(e)}, status=500)
    return JsonResponse({'message': 'Requête invalide'}, status=400)


def unpin_feedback(request, id):
    if request.method == 'POST':
        try:
            feedback = Feedback.objects.get(id=id)
            feedback.is_pinned = False
            feedback.save()
            return JsonResponse({'message': 'Commentaire désépinglé avec succès!'}, status=200)
        except Feedback.DoesNotExist:
            return JsonResponse({'message': 'Commentaire non trouvé'}, status=404)
        except Exception as e:
            return JsonResponse({'message': str(e)}, status=500)
    return JsonResponse({'message': 'Requête invalide'}, status=400)



def cv_det(request):
    return render(request,'test/cv_detail.html')
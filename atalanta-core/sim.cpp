
/***********************************************************************

		Copyright (C) 1991,
		Virginia Polytechnic Institute & State University

		This program was originally written by Mr. Hyung K. Lee
		under the supervision of Dr. Dong S. Ha, in the Bradley
		Department of Electrical Engineering, VPI&SU, in 1991.

		This program is released for research use only. This program,
		or any derivative thereof, may not be reproduced nor used
		for any commercial product without the written permission
		of the authors.

		For detailed information, please contact to

		Dr. Dong S. Ha
		Bradley Department of Electrical Engineering
		Virginia Polytechnic Institute & State University
		Blacksburg, VA 24061

		Ph.: (540) 231-4942
		Fax: (540) 231-3362
		E-Mail: ha@vt.edu
		Web: http://www.ee.vt.edu/ha

		REFERENCE:
		   H. K. Lee and D. S. Ha, "On the Generation of Test Patterns
		   for Combinational Circuits," Technical Report No. 12_93,
		   Dep't of Electrical Eng., Virginia Polytechnic Institute
		   and State University.

***********************************************************************/

/**************************** HISTORY **********************************
 
		atalanta: version 1.0   	 H. K. Lee, 8/15/1991
		atalanta: version 1.1   	 H. K. Lee, 10/5/1992
		atalanta: version 2.0   	 H. K. Lee, 6/30/1997
 
***********************************************************************/

/*---------------------------------------------------------------------
	sim.c
	Top level subroutines for fault simulation.
	Called by main().
----------------------------------------------------------------------*/
#include "stdafx.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/types.h>
//#include <strings.h> //for linux only, change to windows edition as below
#include <string.h>

#include "sim.h"
#include "random.h"
#include "ppsfp.h"
#include "pio.h"
#include "lsim.h"
#include "fsim.h"
#include "fan.h"
#include "define_fault_list.h"
#include "io.h"

#include "parameter.h"
#include "define.h"
#include "macro.h"

extern GATEPTR *g_net, *g_dynamicStack;
extern level g_iAllOne, BITMASK[];
extern level g_test_vectors[MAXTEST / 10][MAXPI + 1];
extern level g_test_vectors1[MAXTEST / 10][MAXPI + 1];
extern level g_test_store[MAXTEST / 10][MAXPI + 1];
extern level g_test_store1[MAXTEST / 10][MAXPI + 1];
extern int g_iPatternOriginVectors[MAXTEST / 10][BITSIZE];
extern int g_iPatternOriginStore[MAXTEST / 10][BITSIZE];
extern int g_iSStack, g_iDStack;
extern status g_iUpdateFlag;
extern level g_PIValues[];
extern char _MODE_SIM, logmode, fillmode;
extern char compact;
extern char g_strFaultOrderMode[];
extern int g_iMaxCompact;
extern char g_cAdaptiveCompact;
extern int g_iAdaptiveCompactEffectiveLimit;
extern int g_iAdaptiveCompactStoppedEarly;
extern double g_lfAdaptiveCompactMinBenefit;
extern FILE *g_fpLogFile;
extern FILE *g_fpFaultTraceFile;
extern FILE *g_fpPatternTraceFile;
extern int *g_PrimaryIn, *g_PrimaryOut;
extern FAULTPTR *g_pFaultList;
extern STACKTYPE g_stack;
extern char g_strVecFileName[FILENAME_MAX];

#define checkbit(word,nth) ((word&BITMASK[nth])!=ALL0)
#define setbit(word,nth) (word|=BITMASK[nth])
#define resetbit(word,nth) (word&=(~BITMASK[nth]))
#define setb0(W0,W1,nth) W0|=BITMASK[nth]; W1&=(~BITMASK[nth]) 
#define setb1(W0,W1,nth) W0&=(~BITMASK[nth]); W1|=BITMASK[nth]
/*
#define setbx(W0,W1,nth) W0|=(BITMASK[nth]); W1|=(BITMASK[nth])
*/
#define setbx(W0,W1,nth) W0&=(~BITMASK[nth]); W1&=(~BITMASK[nth])

//delete_f1ault_fsim
#define removeFaultFromGate(pFault) \
	if (pFault->previous == pFault) \
	{ \
		pFault->gate->pfault = pFault->next; \
		if (pFault->next != NULL) \
		{ \
	   		pFault->next->previous = pFault->next; \
		} \
	} \
	else \
	{ \
		pFault->previous->next = pFault->next; \
		if (pFault->next != NULL) \
		{ \
	   		pFault->next->previous = pFault->previous; \
		} \
	}

#define output0 output
#define is_checkpoint(gate) (gate->type>=PI || gate->outCount>1)

int g_iNoPatternsForOneTime;
//int ntest_each_limit;
extern char gen_all_pat, no_faultsim;

static int get_initial_compaction_patterns(int iPacket, int iBit, int iMaxBitSize)
{
	int iTotal = iPacket * iMaxBitSize + iBit;
	return((iTotal > 0) ? iTotal : 1);
}

static int get_adaptive_compact_limit(int iRequestedLimit, int iNoGate, int iInitialPatterns)
{
	int iLimit = iRequestedLimit;

	if (g_cAdaptiveCompact != 'y' || iRequestedLimit <= 1)
	{
		return(iRequestedLimit);
	}

	if (iInitialPatterns < 20000 || iNoGate < 100000)
	{
		iLimit = 1;
	}
	else if (iRequestedLimit > 3)
	{
		iLimit = 3;
	}

	return((iLimit < iRequestedLimit) ? iLimit : iRequestedLimit);
}

static void log_adaptive_compact_header(const char *pcEngine, int iRequestedLimit, int iEffectiveLimit,
	int iNoGate, int iInitialPatterns)
{
	if (g_cAdaptiveCompact != 'y' || iRequestedLimit <= 1)
	{
		return;
	}

	fprintf(stdout, "Adaptive compaction (%s): requested_limit=%d effective_limit=%d gates=%d initial_patterns=%d min_benefit=%.3lf patterns/sec\n",
		pcEngine, iRequestedLimit, iEffectiveLimit, iNoGate, iInitialPatterns, g_lfAdaptiveCompactMinBenefit);
	if (logmode == 'y')
	{
		fprintf(g_fpLogFile, "Adaptive compaction (%s): requested_limit=%d effective_limit=%d gates=%d initial_patterns=%d min_benefit=%.3lf patterns/sec\n",
			pcEngine, iRequestedLimit, iEffectiveLimit, iNoGate, iInitialPatterns, g_lfAdaptiveCompactMinBenefit);
	}
}

static void log_adaptive_compact_round(const char *pcEngine, int iRound, int iPatterns, int iReduction,
	double lfRoundTime, double lfBenefit, int bStopNext)
{
	if (g_cAdaptiveCompact != 'y')
	{
		return;
	}

	fprintf(stdout, "Adaptive compaction round (%s): round=%d patterns=%d reduction=%d runtime=%.3lf benefit=%.3lf continue=%s\n",
		pcEngine, iRound, iPatterns, iReduction, lfRoundTime, lfBenefit, bStopNext ? "no" : "yes");
	if (logmode == 'y')
	{
		fprintf(g_fpLogFile, "Adaptive compaction round (%s): round=%d patterns=%d reduction=%d runtime=%.3lf benefit=%.3lf continue=%s\n",
			pcEngine, iRound, iPatterns, iReduction, lfRoundTime, lfBenefit, bStopNext ? "no" : "yes");
	}
}

static const char *fault_result_to_string(int iState)
{
	if (iState == TEST_FOUND)
	{
		return("detected");
	}
	if (iState == NO_TEST)
	{
		return("redundant");
	}
	return("aborted");
}

static void log_fault_trace(int iPhase, int iSelectionOrder, int iFaultIndex, FAULTPTR pFault, int iState,
	int iBacktracks, int iBacktrackBudget, double lfFanRuntime, int iGeneratedPatternIndex, int iDetectedByPattern)
{
	GATEPTR pGate = pFault->gate;
	GATEPTR pSite = (pFault->line == OUTFAULT) ? pGate : pGate->inList[pFault->line];
	int iExtraDrops = (iDetectedByPattern > 0) ? iDetectedByPattern - 1 : 0;
	const char *pcGateName = (pGate->hash && pGate->hash->symbol) ? pGate->hash->symbol : "";
	const char *pcSiteName = (pSite->hash && pSite->hash->symbol) ? pSite->hash->symbol : "";

	if (g_fpFaultTraceFile == NULL)
	{
		return;
	}

	fprintf(g_fpFaultTraceFile,
		"%d,%d,%d,%s,%s,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%s,%d,%d,%d,%.6lf,%d,%d,%d,%d\n",
		iPhase,
		iSelectionOrder,
		iFaultIndex,
		pcGateName,
		pcSiteName,
		pFault->line,
		pFault->type,
		pGate->dpi,
		pGate->dpo,
		pSite->dpi,
		pSite->dpo,
		(pGate->outCount > 1),
		(pSite->outCount > 1),
		pGate->outCount,
		pGate->inCount,
		pSite->outCount,
		pSite->inCount,
		pGate->cont0,
		pGate->cont1,
		pSite->cont0,
		pSite->cont1,
		fault_result_to_string(iState),
		iState,
		iBacktracks,
		iBacktrackBudget,
		lfFanRuntime,
		iGeneratedPatternIndex,
		iDetectedByPattern,
		iExtraDrops,
		iGeneratedPatternIndex);
}

static void log_pattern_trace(const char *pcEngine, const char *pcMode, int iShuffleRound,
	int iCompactedPatternIndex, int iOriginPatternIndex, int iDetectedFaults)
{
	if (g_fpPatternTraceFile == NULL)
	{
		return;
	}

	fprintf(g_fpPatternTraceFile, "%s,%s,%d,%d,%d,%d,yes\n",
		pcEngine,
		pcMode,
		iShuffleRound,
		iCompactedPatternIndex,
		iOriginPatternIndex,
		iDetectedFaults);
}

/*------random_sim-----------------------------------------------------
TASK	Performs random similation until n consecutive packets of
	random patterns do not detect any new fault.
----------------------------------------------------------------------*/
int random_fsim(int iNoGate, int iNoPI, int iNoPO, int iMaxLevelAdd2, int iStem, GATEPTR *pStem, level *LFSR,
				int limit, int maxbit, int maxdetect, int *ntest, int *npacket, int *nbit, FILE *test)
{
	int iteration = 0;
	int i, j;
	int profile[BITSIZE];
	int ndetect = 0;

	while (iteration < limit)
	{
		GetPRandompattern(iNoPI, LFSR);
		for (i = 0; i < iNoPI; i++)
		{
			g_net[i]->output1 = g_net[i]->output = LFSR[i];
		}
		evalGatesFromFreeStack();
		for (i = 0; i < maxbit; i++)
			profile[i] = 0;
		if (Fault1_Simulation(iNoGate, iMaxLevelAdd2, iNoPI, iNoPO, iStem, pStem, maxbit, profile) > 0)
		{
			iteration = 0;
			for (i = maxbit - 1; i >= 0; i--)
				if (profile[i] > 0)
				{
					(*ntest)++;
					ndetect += profile[i];
					for (j = 0; j < iNoPI; j++)
						if ((g_net[j]->output1 & BITMASK[i]) != ALL0)
						{
							setbit(g_test_vectors[*npacket][j], *nbit);
						}
						else
						{
							resetbit(g_test_vectors[*npacket][j], *nbit);
						}
					g_iPatternOriginVectors[*npacket][*nbit] = 0;
					if (++(*nbit) == maxbit)
					{
						*nbit = 0; (*npacket)++;
					}
					if (compact == 'n')
					{
						printio(test, iNoPI, iNoPO, i, *ntest);
						if (logmode == 'y')
						{
							fprintf(g_fpLogFile, "test %4d: ", *ntest);
							printinputs(g_fpLogFile, iNoPI, i);
							fprintf(g_fpLogFile, " ");
							printoutputs(g_fpLogFile, iNoPO, i);
							fprintf(g_fpLogFile, " %4d faults detected\n", profile[i]);
						}
					}
				}
			if (ndetect >= maxdetect)
			{
				break;
			}
		}
		else
		{
			iteration++;
		}

		for (i = 0; i <= g_iSStack; i++)
			g_dynamicStack[i]->cobserve = ALL0;
		if (g_iUpdateFlag)
		{
			updateFaultyAndDynamicStack(iNoPI);
			reset(g_iUpdateFlag);
		}
		else
		{
			for (i = g_iDStack; i > g_iSStack; i--)
				g_dynamicStack[i]->freach = 0;
		}
		g_iDStack = g_iSStack;
	}

	return(ndetect);
}

int random_hope(int nopi, int nopo, level *LFSR, int limit, int maxbit, int maxdetect, int *ntest, int *npacket, int *nbit, FILE *test)
{
	int iteration = 0;
	int i, j, n, n1;
	int ndetect = 0;
	int ran_test = 0;

	while (iteration < limit)
	{
		GetPRandompattern(nopi, LFSR);
		for (n = 0, i = maxbit - 1; i >= 0; i--)
		{
			for (j = 0; j < nopi; j++)
				g_PIValues[j] = ((LFSR[j] & BITMASK[i]) == ALL0) ? ZERO : ONE;
			GoodSim_HOPE(++ran_test);
			if ((n1 = FaultSim_HOPE()) > 0)
			{
				n += n1;
				(*ntest)++;
				ndetect += n1;
				for (j = 0; j < nopi; j++)
					if (g_PIValues[j] == ONE)
					{
						setb1(g_test_vectors[*npacket][j], g_test_vectors1[*npacket][j], *nbit);
					}
					else
					{
						setb0(g_test_vectors[*npacket][j], g_test_vectors1[*npacket][j], *nbit);
					}
				g_iPatternOriginVectors[*npacket][*nbit] = 0;
				if (++(*nbit) == maxbit)
				{
					*nbit = 0; (*npacket)++;
				}

				if (compact == 'n')
				{
					fprintf(test, "test %4d: ", *ntest);
					printiovalues(test, g_PrimaryIn, nopi, 'o', 'g', 0);
					fprintf(test, " ");
					printiovalues(test, g_PrimaryOut, nopo, 'o', 'g', 0);
					fprintf(test, "\n");
					if (logmode == 'y')
					{
						fprintf(g_fpLogFile, "test %4d: ", *ntest);
						printiovalues(g_fpLogFile, g_PrimaryIn, nopi, 'o', 'g', 0);
						fprintf(g_fpLogFile, " ");
						printiovalues(g_fpLogFile, g_PrimaryOut, nopo, 'o', 'g', 0);
						fprintf(g_fpLogFile, " %4d faults detected", n);
						fprintf(g_fpLogFile, "\n");
					}
				}

				if (ndetect >= maxdetect)
				{
					break;
				}
			}
		}
		iteration = (n > 0) ? 0 : iteration + 1;
		if (ndetect >= maxdetect)
		{
			break;
		}
	}

	return(ndetect);
}


int random_sim(int nog, int nopi, int nopo, int LEVEL, int nstem, GATEPTR *stem, level *LFSR, int limit, int maxbit, int maxdetect, int *ntest, int *npacket, int *nbit, FILE *test)
{
	if (_MODE_SIM == 'f')
	{
		return(random_fsim(nog, nopi, nopo, LEVEL, nstem, stem, LFSR, limit, maxbit, maxdetect, ntest, npacket, nbit, test));
	}
	else
	{
		return(random_hope(nopi, nopo, LFSR, limit, maxbit, maxdetect, ntest, npacket, nbit, test));
	}
}


int tgen_sim(int iNoGate, int iMaxLevelAdd2, int iNoPI, int iNoPO, int iStem, GATEPTR *pStem, int iNoPatterns,
	int iArrProfile[])
{
	//Return iNoDetected
	//iNoDetected = iArrProfile[0]
	if (_MODE_SIM == 'f') //Default FSIM !!!
	{
		return(Fault0_Simulation(iNoGate, iMaxLevelAdd2, iNoPI, iNoPO, iStem, pStem, 1, iArrProfile));
	}
	else //NOT default: HOPE
	{
		//No parameter at all !!
		GoodSim_HOPE(iNoPatterns); //iNoPatterns is current generated patterns !!
		return(FaultSim_HOPE());
	}
}


void fill_patterns_fsim(char cMode, int iPacket, int iBit, int iNoPI)
{
	int j, iRandom0or1;

	switch (cMode)
	{
	case '0':
		for (j = 0; j < iNoPI; j++)
			switch (g_net[j]->output)
			{
			case ONE:
				setbit(g_test_vectors[iPacket][j], iBit);
				g_net[j]->output1 = ALL1; //ALL1 is useless, 1 is OK !!
				break;
			default: //ZERO & X
				resetbit(g_test_vectors[iPacket][j], iBit);
				g_net[j]->output1 = ALL0;
				break;
			}
		break;
	case '1':
		for (j = 0; j < iNoPI; j++)
			switch (g_net[j]->output)
			{
			case ZERO:
				resetbit(g_test_vectors[iPacket][j], iBit);
				g_net[j]->output1 = ALL0;
				break;
			default: //ONE & X
				setbit(g_test_vectors[iPacket][j], iBit);
				g_net[j]->output1 = ALL1;
				break;
			}
		break;
	case 'r':
	case 'x': //'x' is handled as 'r' because we CANNOT have actual X in FSIM !!
		for (j = 0; j < iNoPI; j++)
			switch (g_net[j]->output)
			{
			case ZERO:
				resetbit(g_test_vectors[iPacket][j], iBit);
				g_net[j]->output1 = ALL0;
				break;
			case ONE:
				setbit(g_test_vectors[iPacket][j], iBit);
				g_net[j]->output1 = ALL1;
				break;
			default: //X
				iRandom0or1 = (int) random() & 01;
				if (iRandom0or1 != 0)
				{
					setbit(g_test_vectors[iPacket][j], iBit);
				}
				else
				{
					resetbit(g_test_vectors[iPacket][j], iBit);
				}
				g_net[j]->output1 = iRandom0or1;
			}
		break;
	}
}

void fill_patterns_hope(char cMode, int iPacket, int iBit, int iNoPI)
{
	int j;

	switch (cMode)
	{
	case '0':
		for (j = 0; j < iNoPI; j++)
			switch (g_net[j]->output)
			{
			case ONE:
				setb1(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ONE;
				break;
			default: //ZERO & X
				setb0(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ZERO;
				break;
			}
		break;
	case '1':
		for (j = 0; j < iNoPI; j++)
			switch (g_net[j]->output)
			{
			case ZERO:
				setb0(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ZERO;
				break;
			default: //ONE & X
				setb1(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ONE;
				break;
			}
		break;
	case 'r':
		for (j = 0; j < iNoPI; j++)
			switch (g_net[j]->output)
			{
			case ZERO:
				setb0(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ZERO;
				break;
			case ONE:
				setb1(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ONE;
				break;
			default: //X
				if ((g_PIValues[j] = (int) random() & 01) != 0)
				{
					setb1(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				}
				else
				{
					setb0(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				}
				break;
			}
		break;
	case 'x':
		for (j = 0; j < iNoPI; j++)
			switch (g_net[j]->output)
			{
			case ZERO:
				setb0(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ZERO;
				break;
			case ONE:
				setb1(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = ONE;
				break;
			default: //X
				setbx(g_test_vectors[iPacket][j], g_test_vectors1[iPacket][j], iBit);
				g_PIValues[j] = X;
				break;
			}
		break;
	}
}


void fill_patterns(char cMode, int iPacket, int iBbit, int iNoPI)
{
	if (_MODE_SIM == 'f') //Default FSIM !!!
	{
		fill_patterns_fsim(cMode, iPacket, iBbit, iNoPI);
	}
	else //NOT default: HOPE
	{
		fill_patterns_hope(cMode, iPacket, iBbit, iNoPI);
	}
}

extern int g_iNoFault;

#define CHECKPOINTMODE 1
#define DEFAULTMODE 0

int testgen(int iNoGate, int iNoPI, int iNoPO, int iMaxLevelAdd2, int iMaxBitSize, int iStem, GATEPTR *pStem,
			int iMaxBackTrack, int bPhase2, int *piNoRedundant, int *piNoOverBackTrack, int *piNoBackTrack,
			int *piNoPatterns, int *piPacket, int *piBit, double *plfFanTime, FILE *fpTestFile)
// int nog, nopi, nopo, LEVEL, maxbits, nstem, maxbacktrack;
// int phase; 	/* 0: static, 1:dynamic unique path sensitization */
// GATEPTR *stem;
// int *nredundant,*noverbacktrack,*nbacktrack,*npacket,*nbit,*ntest;
// double *fantime;
// FILE *test;
{
	//Intialization: piNoPatterns = 0
	int j, iNoBackTrack;
	status iFaultSelectionMode;
	int iLastUndetectedFault;
	int iState;
	int iNoDetected = 0;
	int iSelectionOrder = 0;
	int iGeneratedPatternIndex = 0;
	int iDetectedByPattern = 0;
	int iFaultBacktrackBudget = 0;
	FAULTTYPE *pLastUndetectedFault;
	bool bDone;
	GATEPTR pLastUndetectedGate;
	int iArrProfile[BITSIZE];
	double lfSeconds, lfMinutes, lfRunTime1, lfRunTime2;

	iFaultSelectionMode = DEFAULTMODE; //iFaultSelectionMode always = DEFAULTMODE(0)
	iLastUndetectedFault = g_iNoFault;
	g_iAllOne = ~(ALL1 << 1); //0x00000001
	
	bDone = FALSE;
	while (!bDone)
	{
		// iMaxBackTrack ============== 10 by default !!
		if (iMaxBackTrack == 0) //Impossible
		{
			break;
		}

		/* select any undetected and untried fault */
		pLastUndetectedFault = NULL;
		switch (iFaultSelectionMode)
		{
		case CHECKPOINTMODE: //never come here
// 			while (--iLastUndetectedFault >= 0)
// 				if (is_undetected(g_pFaultList[iLastUndetectedFault]))
// 				{
// 					pLastUndetectedFault = g_pFaultList[iLastUndetectedFault];
// 					pLastUndetectedGate = pLastUndetectedFault->gate;
// 					if (pLastUndetectedFault->line != OUTFAULT)
// 					{
// 						pLastUndetectedGate = pLastUndetectedGate->inList[pLastUndetectedFault->line];
// 					}
// 					if (is_checkpoint(pLastUndetectedGate))
// 					{
// 						break;
// 					}
// 					pLastUndetectedFault = NULL;
// 				}
// 			if (pLastUndetectedFault == NULL)
// 			{
// 				iFaultSelectionMode = DEFAULTMODE;
// 				iLastUndetectedFault = g_iNoFault;
// 			}
			break;

		default: //always come here
			while (--iLastUndetectedFault >= 0)
			{
				if (is_undetected(g_pFaultList[iLastUndetectedFault]))
				{
					//INPUT:      pLastUndetectedFault
					pLastUndetectedFault = g_pFaultList[iLastUndetectedFault];
					break;
				}
			}
			if (pLastUndetectedFault == NULL)
			{
				set(bDone); //OK Phase 1 
			}
		}
		//End Switch !!!
		

		if (pLastUndetectedFault == NULL)
		{
			continue; //OK Phase 2 ----------> EXIT !!!!!
		}
		pLastUndetectedGate = pLastUndetectedFault->gate;
		iSelectionOrder++;

		g_iNoPatternsForOneTime = 0;
		if (no_faultsim == 'y') //NOT default !!!
		{
			printfault(fpTestFile, pLastUndetectedFault, 0);
			if (logmode == 'y')
			{
				printfault(g_fpLogFile, pLastUndetectedFault, 0);
			}
		}
		fprintf(stderr, "iLastUndetectedFault=%d\n", iLastUndetectedFault);
		getTime(&lfMinutes, &lfSeconds, &lfRunTime1);
		iFaultBacktrackBudget = iMaxBackTrack;
		if (strcmp(g_strFaultOrderMode, "history") == 0 && pLastUndetectedFault->history_backtrack_budget > 0)
		{
			iFaultBacktrackBudget = pLastUndetectedFault->history_backtrack_budget;
		}


		/* test pattern generation using fan */
		if (bPhase2 == FALSE) //Default !!
		{
			//iMaxBackTrack == 10
			iState = fan(iNoGate, iMaxLevelAdd2, iNoPI, iNoPO, pLastUndetectedFault, iFaultBacktrackBudget, &iNoBackTrack);
			//Output: iState & g_iPatternsForOneTime & iNoBackTrack & g_net[i] (PI, Test Patterns !!!)
		}
		else //bPhase2 == TRUE
		{
			//STOP*****************************************STOP
			//iMaxBackTrack == xx
			iState = fan1(iNoGate, iMaxLevelAdd2, iNoPI, iNoPO, pLastUndetectedFault, iFaultBacktrackBudget, &iNoBackTrack);
			//Output: iState & g_iPatternsForOneTime & iNoBackTrack & g_net[i] (PI, Test Patterns !!!)
		}
		
		(*piNoBackTrack) += iNoBackTrack;

		getTime(&lfMinutes, &lfSeconds, &lfRunTime2);
		(*plfFanTime) += (lfRunTime2 - lfRunTime1);
		iGeneratedPatternIndex = 0;
		iDetectedByPattern = 0;

		if (no_faultsim == 'y') ///////////////////////////NOT default
		{
			//STOP*********************STOP
			(*piNoPatterns) += g_iNoPatternsForOneTime;
			if (g_iNoPatternsForOneTime > 0) //iState == TEST_FOUND
			{
				iGeneratedPatternIndex = *piNoPatterns;
				iDetectedByPattern = 1;
				pLastUndetectedFault->detected = DETECTED;
				iNoDetected++;
			}
			else if (iState == NO_TEST)
			{
				/* redundant faults */
				pLastUndetectedFault->detected = REDUNDANT;
				(*piNoRedundant)++;
			}
			else //iState == OVER_BACKTRACK
			{
				/* over backtracking */
				pLastUndetectedFault->detected = PROCESSED;
				(*piNoOverBackTrack)++;
			}
		}



		
		//no_faultsim != 'y'
		else if (iState == TEST_FOUND) //////////////////////////Default !!!
		{
			/* fault is detected, delete the detected fault from fault list */
			pLastUndetectedFault->detected = PROCESSED;
			(*piNoPatterns)++;
			iGeneratedPatternIndex = *piNoPatterns;

			/*
			pLastUndetectedFault->detected=DETECTED;
			pLastUndetectedGate->nfault--;
			iNoDetected++;
			*/
			
			/* assign random zero and ones to the unassigned bits */
			fill_patterns(fillmode, *piPacket, *piBit, iNoPI);
			//OUTPUT: g_net[i] (PI)
			g_iPatternOriginVectors[*piPacket][*piBit] = iGeneratedPatternIndex;

			
			if (_MODE_SIM == 'f') //Default FSIM !!!
			{
				for (j = 0; j < iNoPI; j++)
				{
					reset(g_net[j]->changed);
					reset(g_net[j]->freach);
					g_net[j]->cobserve = ALL0;
					g_net[j]->output = g_net[j]->output1; //Random-assigned values !!
				}
			}
			else //NOT default: HOPE
			{
				for (j = 0; j < iNoGate; j++)
				{
					reset(g_net[j]->changed);
					reset(g_net[j]->freach);
				}
			}
			
			if (++(*piBit) == iMaxBitSize)
			{
				*piBit = 0; (*piPacket)++;
			}
			clear(g_stack);

			/* fault simulation */
			//iArrProfile[0] = return of tgen_sim, so weird !!
			//piNoPatterns NO USE !!!
			iArrProfile[0] = tgen_sim(iNoGate, iMaxLevelAdd2, iNoPI, iNoPO, iStem, pStem, *piNoPatterns, iArrProfile);
			iNoDetected += iArrProfile[0];
			iDetectedByPattern = iArrProfile[0];


			//Print functions, no big use !!
			if (compact == 'n') //////////////NOT default, default value is 's'!!
			{
				//STOP***********************************STOP
				if (_MODE_SIM == 'f') //Default !!!
				{
					/*printio(test,nopi,nopo,j,*ntest);KHB*/
					printio(fpTestFile, iNoPI, iNoPO, 0, *piNoPatterns);
					if (logmode == 'y') //NOT default !!!
					{
						fprintf(g_fpLogFile, "test %4d: ", *piNoPatterns);
						printinputs(g_fpLogFile, iNoPI, 0);
						fprintf(g_fpLogFile, " ");
						printoutputs(g_fpLogFile, iNoPO, 0);
						fprintf(g_fpLogFile, " %4d faults detected\n", iArrProfile[0]);
					}
				}
				else
				{
					fprintf(fpTestFile, "test %4d: ", *piNoPatterns);
					printiovalues(fpTestFile, g_PrimaryIn, iNoPI, 'o', 'g', 0);
					fprintf(fpTestFile, " ");
					printiovalues(fpTestFile, g_PrimaryOut, iNoPO, 'o', 'g', 0);
					fprintf(fpTestFile, "\n");
					if (logmode == 'y')
					{
						fprintf(g_fpLogFile, "test %4d: ", *piNoPatterns);
						printiovalues(g_fpLogFile, g_PrimaryIn, iNoPI, 'o', 'g', 0);
						fprintf(g_fpLogFile, " ");
						printiovalues(g_fpLogFile, g_PrimaryOut, iNoPO, 'o', 'g', 0);
						fprintf(g_fpLogFile, " %4d faults detected", iArrProfile[0]);
						fprintf(g_fpLogFile, "\n");
					}
				}
			}

			if (pLastUndetectedFault->detected != DETECTED) //Why?? So Magic..
			{
				printf("Error in test generation\n");
			}
		}
		else if (iState == NO_TEST)
		{
			/* redundant faults */
			pLastUndetectedFault->detected = REDUNDANT;
			(*piNoRedundant)++;
			if (_MODE_SIM == 'f') //Default !!                 f:FSIM h:HOPE
			{
				removeFaultFromGate(pLastUndetectedFault);
				if (--pLastUndetectedGate->nfault == 0)
				{
					set(g_iUpdateFlag);
				}
			}
		}
		else //iState == OVER_BACKTRACK
		{
			/* over backtracking */
			(*piNoOverBackTrack)++;
			pLastUndetectedFault->detected = PROCESSED;
		}
		log_fault_trace(bPhase2 ? 2 : 1, iSelectionOrder, iLastUndetectedFault, pLastUndetectedFault, iState,
			iNoBackTrack, iFaultBacktrackBudget, lfRunTime2 - lfRunTime1, iGeneratedPatternIndex, iDetectedByPattern);
	}

	return(iNoDetected);
}


//random_test_fsim
void randomizePatterns_FSIM(level test_store[][MAXPI + 1], level test_vectors[][MAXPI + 1], int ipacket, int iBit,
	int iNoPI)
{
	//INPUT:  test_store, ipacket, iBit
	//OUTPUT:  test_vectors
	int array[MAXTEST *BITSIZE];
	int array1[MAXTEST *BITSIZE];
	int i, j, x, iGlobalBit, k, B, iBit_Local = 0, iPacket_Local = 0;
	int iMaxBitSize = BITSIZE;
	//FILE *fp;
	fprintf(stderr, "%d ", iNoPI);
	iNoPI = 3357; //what the hell is this??

	iGlobalBit = 32 * ipacket + iBit; //ipacket <= MAXTEST - 1, include ipacket, NOT include iBit !!!
	for (i = 0; i < iGlobalBit; i++)
		array[i] = i;

	j = 0;
	for (i = iGlobalBit - 1; i >= 0; i--)
	{
		x = random() % (i + 1);
		array1[j] = array[x];
		array[x] = array[i];
		j++;
	}
	for (i = 0; i < iGlobalBit; i++)
	{
		x = array1[i];
		k = x / 32;
		B = x % 32;
		for (j = 0; j < iNoPI; j++)
		{
			//fp=fopen("b18.trace","w");
			//fprintf(fp,"%d,%d\n",k,j);
			if ((test_store[k][j] & BITMASK[B]) != ALL0) //test_store[k][j].BITMASK[B] == 1!!
			{
				setbit(test_vectors[iPacket_Local][j], iBit_Local);
			}
			else
			{
				resetbit(test_vectors[iPacket_Local][j], iBit_Local);
			}
			//test_store -> test_vectors, totally number: iPacket_Local * 32 + iBit_Local
		}
		g_iPatternOriginVectors[iPacket_Local][iBit_Local] = g_iPatternOriginStore[k][B];
		if (++iBit_Local == iMaxBitSize) //iMaxBitSize == 32 !!!
		{
			iBit_Local = 0;
			iPacket_Local++;
		}
	}
}


int reverse_fsim(int nog, int nopi, int nopo, int LEVEL, int nstem, GATEPTR *stem, int nof, int *ndet, int npacket, int nbit, int maxbits, FILE *test)
{
	int i, j, k, n;
	int nrestoredfault;
	int ndetect = 0;
	int no_test = 0;
	int ncomp = INFINITY, stop = ONE;
	int bit = 0, packet = 0;
	int profile[BITSIZE];
	int store = 0; //iArrArray[MAXTEST] not used
	//int bDone, bFlagBit;

	for (i = 0; i < nog; i++)
	{
		g_net[i]->nfault = 0;
		g_net[i]->pfault = NULL;
	}
	if ((nrestoredfault = restoreUndetectedState_FSIM(nof)) < 0)
	{
		printf("error occurred in restoration of fault list\n");
		exit(0);
	}

	initGateStackAndFreach(nog, LEVEL, nopi);

	reset(g_iUpdateFlag);
	if (nbit == 0)
	{
		--npacket; nbit = maxbits;
	}

	/* reverse fault simulation */
	k = npacket + 1;
	while (--k >= 0)
	{
		if (ndetect >= nrestoredfault)
		{
			break;
		}
		if (k < npacket)
		{
			nbit = maxbits;
		}
		if (nbit == BITSIZE)
		{
			g_iAllOne = ALL1;
		}
		else
		{
			g_iAllOne = ~(ALL1 << nbit);
		}

		for (j = 0; j < nopi; j++)
			g_net[j]->output1 = g_net[j]->output = g_test_vectors[k][j];
		evalGatesFromFreeStack();

		for (i = 0; i < nbit; i++)
			profile[i] = 0;
		if ((n = Fault1_Simulation(nog, LEVEL, nopi, nopo, nstem, stem, nbit, profile)) > 0)
		{
			ndetect += n;

			/* print out test files */
			for (i = nbit - 1; i >= 0; i--)
				if (profile[i] > 0)
				{
					no_test++;
					if (compact == 'r')
					{
						printio(test, nopi, nopo, i, no_test);
						log_pattern_trace("FSIM", "reverse", 0, no_test, g_iPatternOriginVectors[k][i], profile[i]);
						if (logmode == 'y')
						{
							fprintf(g_fpLogFile, "test %4d: ", no_test);
							printinputs(g_fpLogFile, nopi, i);
							fprintf(g_fpLogFile, " ");
							printoutputs(g_fpLogFile, nopo, i);
							fprintf(g_fpLogFile, " %4d faults detected\n", profile[i]);
						}
					}
				}
		}

		for (i = 0; i <= g_iSStack; i++)
			g_dynamicStack[i]->cobserve = ALL0;
		if (g_iUpdateFlag)
		{
			updateFaultyAndDynamicStack(nopi);
			reset(g_iUpdateFlag);
		}
		else
		{
			for (i = g_iDStack; i > g_iSStack; i--)
				g_dynamicStack[i]->freach = 0;
		}
		g_iDStack = g_iSStack;
	}

	*ndet = ndetect;
	return(no_test);
}


int shuffle_fsim(int iNoGate, int iNoPI, int iNoPO, int iMaxLevelAdd2, int iStem, GATEPTR *pStem, int iNoFault,
				 int *piShuffle, int *piDetected, int iPacket, int iBit, int iMaxBitSize, FILE *fpTestFile)
{
	int i, j, iPacketIndex, iNoDetectedOnce;
	int iNoRestoredFault;
	int iNoDetected = 0;
	int iNoPatterns = 0;
	int iCompactCnt = INFINITY, iStop = ONE; //Why iCompactCnt = INFINITY, NO Use at all !!
	int iBit_Local = 0, iPacket_Local = 0;
	int iArrNoDetected[BITSIZE];
	int iArrArray[MAXTEST], iStore = 0;
	int bDone, bRunShuffle;
	int iEffectiveCompactLimit, iInitialPatterns, iPreviousPatterns = (-1);
	int bAdaptiveStopNext = FALSE;
	double lfMinutes, lfSeconds, lfRoundStart, lfRoundEnd, lfRoundTime, lfBenefit;

	/***********/
	FILE *fpVecFile;
	if ((fpVecFile = fopen(g_strVecFileName, "w")) != NULL)
	{
	}
	/**************/

	iInitialPatterns = get_initial_compaction_patterns(iPacket, iBit, iMaxBitSize);
	iEffectiveCompactLimit = get_adaptive_compact_limit(g_iMaxCompact, iNoGate, iInitialPatterns);
	g_iAdaptiveCompactEffectiveLimit = iEffectiveCompactLimit;
	g_iAdaptiveCompactStoppedEarly = FALSE;
	log_adaptive_compact_header("FSIM", g_iMaxCompact, iEffectiveCompactLimit, iNoGate, iInitialPatterns);

	for (i = 0; i <= iEffectiveCompactLimit; i++) //g_iMaxCompact == 2 by default
	{
		iArrArray[i] = 0; //allocate 10000, only use 3 by default
	}
	reset(bDone);
	bRunShuffle = FALSE;
	*piShuffle = 0;

	/* shuffle fault simulation */
	while ((!bDone)) //One shuffle
	{
		getTime(&lfMinutes, &lfSeconds, &lfRoundStart);
		(*piShuffle)++;
		for (i = 0; i < iNoGate; i++)
		{
			g_net[i]->nfault = 0;
			g_net[i]->pfault = NULL; //Just desert the pfault!!
		}
		if ((iNoRestoredFault = restoreUndetectedState_FSIM(iNoFault)) < 0) //IMPOSSIBLE !!
		{
			//STOP*********************************STOP
			printf("error occurred in restoration of fault list\n");
			exit(0);
		}

		initGateStackAndFreach(iNoGate, iMaxLevelAdd2, iNoPI);

		reset(g_iUpdateFlag);
		if (bRunShuffle == TRUE)
		{
			iBit = iBit_Local;   
			iPacket = iPacket_Local;
			/*shuffles the fpTestFile patterns and stores it back in the random fashion*/
			randomizePatterns_FSIM(g_test_store, g_test_vectors, iPacket_Local, iBit_Local, iNoPI);
			//g_test_store -----------> g_test_vectors
			iBit_Local = iPacket_Local = 0;
			if (bAdaptiveStopNext == TRUE)
			{
				iStop = STOP;
			}
			else
			{
				for (iCompactCnt = 0; iCompactCnt <= iEffectiveCompactLimit - 1; iCompactCnt++) //iCompactCnt = 0, 1
				{
					iStop = STOP;
					if (iArrArray[iCompactCnt] != iArrArray[iCompactCnt + 1])
					{
						iStop = TWO;
						break;
					}
				}
			}
		}

		iNoPatterns = 0;
		iNoDetected = 0;

		if (iBit == 0)
		{
			--iPacket;
			iBit = iMaxBitSize;
		}
		iPacketIndex = iPacket + 1;
		
		while (--iPacketIndex >= 0)
		{
			if (iNoDetected >= iNoRestoredFault) //End condition!!!
			{
				break;
			}
			if (iPacketIndex < iPacket)
			{
				iBit = iMaxBitSize;
			}
			//
			//Finish Initializing iPacketIndex & iBit !!!
			//
			if (iBit == BITSIZE) //g_iAllOne has iBit's "1" in the right!!!
			{
				g_iAllOne = ALL1;
			}
			else
			{
				g_iAllOne = ~(ALL1 << iBit);
			}

			for (j = 0; j < iNoPI; j++)
			{
			 	//LOAD INPUTS!!!
				//g_test_vectors -----> g_net
				g_net[j]->output1 = g_net[j]->output = g_test_vectors[iPacketIndex][j];
			}
				
			evalGatesFromFreeStack(); //Free gates simulates first !!

			for (i = 0; i < iBit; i++)
			{
				iArrNoDetected[i] = 0;
			}
			
			if ((iNoDetectedOnce = Fault1_Simulation(iNoGate, iMaxLevelAdd2, iNoPI, iNoPO, iStem, pStem, iBit, iArrNoDetected)) > 0)
			{
				iNoDetected += iNoDetectedOnce;  //Multiple faults !!

				/* print out fpTestFile files */
				for (i = iBit - 1; i >= 0; i--)
				{
					if (iArrNoDetected[i] > 0) //Effective pattern found!!!
					{
						iNoPatterns++; //iBit's patterns !!
						if (iStop == STOP) //Always: iStop == STOP, Only one time to execute.
						{
							printio(fpTestFile, iNoPI, iNoPO, i, iNoPatterns); //Print compacted patterns!!!
							log_pattern_trace("FSIM", "shuffle", *piShuffle, iNoPatterns, g_iPatternOriginVectors[iPacketIndex][i], iArrNoDetected[i]);

							printinputs(fpVecFile, iNoPI, i); //Print compacted patterns!!!
							fprintf(fpVecFile, "\n");

							if (logmode == 'y')
							{
								fprintf(g_fpLogFile, "fpTestFile %4d: ", iNoPatterns);
								printinputs(g_fpLogFile, iNoPI, i);
								fprintf(g_fpLogFile, " ");
								printoutputs(g_fpLogFile, iNoPO, i);
								fprintf(g_fpLogFile, " %4d faults detected\n", iArrNoDetected[i]);
							}
							set(bDone); //OK!!!!
						}
						bRunShuffle = TRUE;
						for (j = 0; j < iNoPI; j++)
						{
							//Export the modified inputs !!
							if ((g_net[j]->output1 & BITMASK[i]) != ALL0) //g_net -------> g_test_store
							{
								setbit(g_test_store[iPacket_Local][j], iBit_Local);
							}
							else
							{
								resetbit(g_test_store[iPacket_Local][j], iBit_Local);
							}
						}
						g_iPatternOriginStore[iPacket_Local][iBit_Local] = g_iPatternOriginVectors[iPacketIndex][i];
						if (++iBit_Local == iMaxBitSize)
						{
							iBit_Local = 0; iPacket_Local++;
						}
					}
				}
			}


			for (i = 0; i <= g_iSStack; i++)
			{
				g_dynamicStack[i]->cobserve = ALL0;
			}
			
			if (g_iUpdateFlag)
			{
				//Clear All Freach !!
				updateFaultyAndDynamicStack(iNoPI); //g_faultyGatesStack ----> freach & g_faultyGatesStack & g_dynamicStack
				reset(g_iUpdateFlag);
			}
			else
			{
				//Clear Only pDominator's Freach !!
				for (i = g_iDStack; i > g_iSStack; i--)
				{
					g_dynamicStack[i]->freach = 0;
				}
			}
			g_iDStack = g_iSStack;
		}

		getTime(&lfMinutes, &lfSeconds, &lfRoundEnd);
		lfRoundTime = lfRoundEnd - lfRoundStart;
		lfBenefit = 0.0;
		if (iPreviousPatterns >= 0 && !bDone)
		{
			int iReduction = iPreviousPatterns - iNoPatterns;
			if (lfRoundTime > 0.0)
			{
				lfBenefit = (double)iReduction / lfRoundTime;
			}
			else if (iReduction > 0)
			{
				lfBenefit = (double)iReduction;
			}
			if (g_cAdaptiveCompact == 'y' && g_iMaxCompact > 1 &&
				((*piShuffle) >= iEffectiveCompactLimit + 1 ||
				iReduction <= 0 || lfBenefit < g_lfAdaptiveCompactMinBenefit))
			{
				bAdaptiveStopNext = TRUE;
				g_iAdaptiveCompactStoppedEarly = TRUE;
			}
			log_adaptive_compact_round("FSIM", *piShuffle, iNoPatterns, iReduction, lfRoundTime, lfBenefit, bAdaptiveStopNext);
		}
		iPreviousPatterns = iNoPatterns;

		if (iStore == iEffectiveCompactLimit + 1) //iStore == 0, 1, 2
		{
			iStore = 0;
		}
		iArrArray[iStore] = iNoPatterns;
		iStore++;
	}
	/************/
	fprintf(fpVecFile, "END\n");
	fclose(fpVecFile);
	*piDetected = iNoDetected;
	return(iNoPatterns);
}

void randomizePatterns_HOPE(level test_store[][MAXPI + 1], level test_store1[][MAXPI + 1], level test_vectors[][MAXPI + 1],
					  level test_vectors1[][MAXPI + 1], int iPacket, int iBit, int iNoPI)
{
	int array[40 * BITSIZE];
	int array1[40 * BITSIZE];
	int i, j, x, iGlobalBit, k, B, iBit_Local = 0, iPacket_Local = 0;
	int iMaxBitSize = BITSIZE;

	iGlobalBit = 32 * iPacket + iBit;
	for (i = 0; i < iGlobalBit; i++)
		array[i] = i;

	j = 0;
	for (i = iGlobalBit - 1; i >= 0; i--)
	{
		x = random() % (i + 1);
		array1[j] = array[x];
		array[x] = array[i];
		j++;
	}
	for (i = 0; i < iGlobalBit; i++)
	{
		x = array1[i];
		k = x / 32;
		B = x % 32;
		for (j = 0; j < iNoPI; j++)
		{
			if ((test_store[k][j] & BITMASK[B]) != ALL0)
			{
				setbit(test_vectors[iPacket_Local][j], iBit_Local);
			}
			else
			{
				resetbit(test_vectors[iPacket_Local][j], iBit_Local);
			}
			if ((test_store1[k][j] & BITMASK[B]) != ALL0)
			{
				setbit(test_vectors1[iPacket_Local][j], iBit_Local);
			}
			else
			{
				resetbit(test_vectors1[iPacket_Local][j], iBit_Local);
			}
		}
		g_iPatternOriginVectors[iPacket_Local][iBit_Local] = g_iPatternOriginStore[k][B];
		if (++iBit_Local == iMaxBitSize)
		{
			iBit_Local = 0;
			iPacket_Local++;
		}
	}
}


extern FAULTPTR g_pPotentialFault, g_pTailFault;

int reverse_hope(int nog, int nopi, int nopo, int nof, int *ndet, int npacket, int nbit, int maxbits, FILE *test)
{
	int i, j, k, n;
	level v1, v2;
	int nrestoredfault;
	int ndetect = 0;
	int no_test = 0;
	int ncomp = INFINITY, stop = ONE;
	int bit = 0, packet = 0;
	int store = 0; //narray[MAXTEST] not used
	//int done, flag_bit;

	if ((nrestoredfault = restoreUndetectedState_HOPE(nof)) < 0)
	{
		printf("error occurred in restoration of fault list\n");
		exit(0);
	}
	g_pPotentialFault = g_pTailFault;
	for (i = 0; i < nog; i++)
	{
		reset(g_net[i]->changed);
	}

	if (nbit == 0)
	{
		--npacket; nbit = maxbits;
	}

	/* reverse fault simulation */
	k = npacket + 1;
	while (--k >= 0)
	{
		if (ndetect >= nrestoredfault)
		{
			break;
		}
		if (k < npacket)
		{
			nbit = maxbits;
		}
		for (i = nbit - 1; i >= 0; i--)
		{
			for (j = 0; j < nopi; j++)
			{
				v1 = ((g_test_vectors[k][j] & BITMASK[i]) == ALL0) ? ZERO : ONE;
				v2 = ((g_test_vectors1[k][j] & BITMASK[i]) == ALL0) ? ZERO : ONE;
				g_PIValues[j] = (v1 == ONE) ? ZERO : (v2 == ONE) ? ONE : X;
			}
			GoodSim_HOPE(2);
			if ((n = FaultSim_HOPE()) > 0)
			{
				ndetect += n;
				no_test++;
				if (compact == 'r')
				{
					fprintf(test, "test %4d: ", no_test);
					printiovalues(test, g_PrimaryIn, nopi, 'o', 'g', 0);
					fprintf(test, " ");
					printiovalues(test, g_PrimaryOut, nopo, 'o', 'g', 0);
					fprintf(test, "\n");
					if (logmode == 'y')
					{
						fprintf(g_fpLogFile, "test %4d: ", no_test);
						printiovalues(g_fpLogFile, g_PrimaryIn, nopi, 'o', 'g', 0);
						fprintf(g_fpLogFile, " ");
						printiovalues(g_fpLogFile, g_PrimaryOut, nopo, 'o', 'g', 0);
						fprintf(g_fpLogFile, " %4d faults detected", n);
						fprintf(g_fpLogFile, "\n");
					}
				}
				if (ndetect >= nrestoredfault)
				{
					break;
				}
			}
		}
	}

	*ndet = ndetect;
	return(no_test);
}


int shuffle_hope(int iNoGate, int iNoPI, int iNoPO, int iNoFault, int *piShuffle, int *piDetected, int iPacket,
						int iBit, int iMaxBitSize, FILE *fpTestFile)
{
	int i, j, iPacketIndex, iNoDetectedOnce;
	level iValue1, iValue2;
	int iNoRestoredFault;
	int iNoDetected = 0;
	int iNoPatterns = 0;
	int iCompactCnt = INFINITY, iStop = ONE; //Why iCompactCnt = INFINITY, NO Use at all !!
	int iBit_Local = 0, iPacket_Local = 0;
	int iArrArray[MAXTEST], iStore = 0;
	int bDone, bRunShuffle;
	int iEffectiveCompactLimit, iInitialPatterns, iPreviousPatterns = (-1);
	int bAdaptiveStopNext = FALSE;
	double lfMinutes, lfSeconds, lfRoundStart, lfRoundEnd, lfRoundTime, lfBenefit;

	iInitialPatterns = get_initial_compaction_patterns(iPacket, iBit, iMaxBitSize);
	iEffectiveCompactLimit = get_adaptive_compact_limit(g_iMaxCompact, iNoGate, iInitialPatterns);
	g_iAdaptiveCompactEffectiveLimit = iEffectiveCompactLimit;
	g_iAdaptiveCompactStoppedEarly = FALSE;
	log_adaptive_compact_header("HOPE", g_iMaxCompact, iEffectiveCompactLimit, iNoGate, iInitialPatterns);

	for (i = 0; i <= iEffectiveCompactLimit; i++) //g_iMaxCompact == 2 by default
	{
		iArrArray[i] = 0; //allocate 10000, only use 3 by default
	}
	reset(bDone);
	bRunShuffle = FALSE;
	*piShuffle = 0;

	/* shufle fault simulation */
	while ((!bDone)) //One shuffle
	{
		getTime(&lfMinutes, &lfSeconds, &lfRoundStart);
		(*piShuffle)++;
		if ((iNoRestoredFault = restoreUndetectedState_HOPE(iNoFault)) < 0) //IMPOSSIBLE !!
		{
			//STOP*********************************STOP
			printf("error occurred in restoration of fault list\n");
			exit(0);
		}
		g_pPotentialFault = g_pTailFault;
		for (i = 0; i < iNoGate; i++)
		{
			reset(g_net[i]->changed);
		}

		if (bRunShuffle == TRUE)
		{
			iBit = iBit_Local;   
			iPacket = iPacket_Local;
			/*shuffles the fpTestFile patterns and stores it back in the random fashion*/
			randomizePatterns_HOPE(g_test_store, g_test_store1, g_test_vectors, g_test_vectors1, iPacket_Local, iBit_Local, iNoPI);
			//g_test_store -----------> g_test_vectors
			iBit_Local = iPacket_Local = 0;
			if (bAdaptiveStopNext == TRUE)
			{
				iStop = STOP;
			}
			else
			{
				for (iCompactCnt = 0; iCompactCnt <= iEffectiveCompactLimit - 1; iCompactCnt++) //iCompactCnt = 0, 1
				{
					iStop = STOP;
					if (iArrArray[iCompactCnt] != iArrArray[iCompactCnt + 1])
					{
						iStop = TWO;
						break;
					}
				}
			}
		}

		iNoPatterns = 0;
		iNoDetected = 0;

		if (iBit == 0)
		{
			--iPacket;
			iBit = iMaxBitSize;
		}
		iPacketIndex = iPacket + 1;
		
		while (--iPacketIndex >= 0)
		{
			if (iNoDetected >= iNoRestoredFault) //End condition!!!
			{
				break;
			}
			if (iPacketIndex < iPacket)
			{
				iBit = iMaxBitSize;
			}
			//
			//Finish Initializing iPacketIndex & iBit !!!
			//
			
			for (i = iBit - 1; i >= 0; i--)
			{
				for (j = 0; j < iNoPI; j++)
				{
					//LOAD INPUTS!!!
					//g_test_vectors &  g_test_vectors1 -----> g_PIValues
					iValue1 = ((g_test_vectors[iPacketIndex][j] & BITMASK[i]) == ALL0) ? ZERO : ONE;
					iValue2 = ((g_test_vectors1[iPacketIndex][j] & BITMASK[i]) == ALL0) ? ZERO : ONE;
					g_PIValues[j] = (iValue1 == ONE) ? ZERO : (iValue2 == ONE) ? ONE : X;
					//g_test_vectors's 1-----> 0
					//g_test_vectors1's 1 -----> 1
					//both 0 -----> X
				}
				GoodSim_HOPE(2);
				if ((iNoDetectedOnce = FaultSim_HOPE()) > 0)
				{
					iNoDetected += iNoDetectedOnce; //Multiple faults !!
					iNoPatterns++; //Single pattern !!
					if (iStop == STOP)
					{
						fprintf(fpTestFile, "fpTestFile %4d: ", iNoPatterns);
						printiovalues(fpTestFile, g_PrimaryIn, iNoPI, 'o', 'g', 0);
						fprintf(fpTestFile, " ");
						printiovalues(fpTestFile, g_PrimaryOut, iNoPO, 'o', 'g', 0);
						fprintf(fpTestFile, "\n");
						log_pattern_trace("HOPE", "shuffle", *piShuffle, iNoPatterns, g_iPatternOriginVectors[iPacketIndex][i], iNoDetectedOnce);
						if (logmode == 'y')
						{
							fprintf(g_fpLogFile, "fpTestFile %4d: ", iNoPatterns);
							printiovalues(g_fpLogFile, g_PrimaryIn, iNoPI, 'o', 'g', 0);
							fprintf(g_fpLogFile, " ");
							printiovalues(g_fpLogFile, g_PrimaryOut, iNoPO, 'o', 'g', 0);
							fprintf(g_fpLogFile, " %4d faults detected", iNoDetectedOnce);
							fprintf(g_fpLogFile, "\n");
						}
						set(bDone);
					}
					bRunShuffle = TRUE;
					for (j = 0; j < iNoPI; j++)
					{
						//Export the modified inputs !!
						switch (g_PIValues[j]) //g_PIValues -------> g_test_store & g_test_store1
						{
						case ONE:
							setb1(g_test_store[iPacket_Local][j], g_test_store1[iPacket_Local][j], iBit_Local);
							break;
						case ZERO:
							setb0(g_test_store[iPacket_Local][j], g_test_store1[iPacket_Local][j], iBit_Local);
							break;
						default:
							setbx(g_test_store[iPacket_Local][j], g_test_store1[iPacket_Local][j], iBit_Local);
							break;
						}
					}
					g_iPatternOriginStore[iPacket_Local][iBit_Local] = g_iPatternOriginVectors[iPacketIndex][i];
					if (++iBit_Local == iMaxBitSize)
					{
						iBit_Local = 0; iPacket_Local++;
					}
				}
				if (iNoDetected >= iNoRestoredFault)
				{
					break;
				}
			}
		}
		
		getTime(&lfMinutes, &lfSeconds, &lfRoundEnd);
		lfRoundTime = lfRoundEnd - lfRoundStart;
		lfBenefit = 0.0;
		if (iPreviousPatterns >= 0 && !bDone)
		{
			int iReduction = iPreviousPatterns - iNoPatterns;
			if (lfRoundTime > 0.0)
			{
				lfBenefit = (double)iReduction / lfRoundTime;
			}
			else if (iReduction > 0)
			{
				lfBenefit = (double)iReduction;
			}
			if (g_cAdaptiveCompact == 'y' && g_iMaxCompact > 1 &&
				((*piShuffle) >= iEffectiveCompactLimit + 1 ||
				iReduction <= 0 || lfBenefit < g_lfAdaptiveCompactMinBenefit))
			{
				bAdaptiveStopNext = TRUE;
				g_iAdaptiveCompactStoppedEarly = TRUE;
			}
			log_adaptive_compact_round("HOPE", *piShuffle, iNoPatterns, iReduction, lfRoundTime, lfBenefit, bAdaptiveStopNext);
		}
		iPreviousPatterns = iNoPatterns;

		if (iStore == iEffectiveCompactLimit + 1) //iStore == 0, 1, 2
		{
			iStore = 0;
		}
		iArrArray[iStore] = iNoPatterns;
		iStore++;
	}
	
	*piDetected = iNoDetected;
	return(iNoPatterns);
}

int compact_test(int iNoGate, int iNoPI, int iNoPO, int iMaxLevelAdd2, int iStem, GATEPTR *pStem, int iNoFault,
	int *piShuffle, int *piDetected, int iPacket, int iBit, int iMaxBitSize, FILE *fpTestFile)
{
	*piShuffle = 0;
	if (_MODE_SIM == 'f') //no "-H" flag
	{
		if (compact == 's') //no "-N" flag, with "-c >0", default = 2 ***********************default option!!
		{
			return(shuffle_fsim(iNoGate, iNoPI, iNoPO, iMaxLevelAdd2, iStem, pStem, iNoFault, piShuffle, piDetected,
				iPacket, iBit, iMaxBitSize, fpTestFile));
		}
		else //compact == 'r' //no "-N" flag, with "-c 0"
		{
			return(reverse_fsim(iNoGate, iNoPI, iNoPO, iMaxLevelAdd2, iStem, pStem, iNoFault, piDetected,
				iPacket, iBit, iMaxBitSize, fpTestFile));
		}
	}
	else //_MODE_SIM = 'h'
	{
		if (compact == 's') //no "-N" flag, with "-c >0"
		{
			return(shuffle_hope(iNoGate, iNoPI, iNoPO, iNoFault, piShuffle, piDetected, iPacket, iBit, iMaxBitSize,
				fpTestFile));
		}
		else //compact == 'r' //no "-N" flag, with "-c 0"
		{
			return(reverse_hope(iNoGate, iNoPI, iNoPO, iNoFault, piDetected, iPacket, iBit, iMaxBitSize, fpTestFile));
		}
	}
}


extern FILE *g_fpTestFile;
char Dlevel_to_string[][5] =
{
	"0", "1", "x", "1", "0"
};
void Dprintio(FILE *test, int nopi, int nopo, int no)
{
	int i;

	fprintf(test, "   %4d: ", no);
	for (i = 0; i < nopi; i++)
	{
		fprintf(test, "%s", Dlevel_to_string[g_net[g_PrimaryIn[i]]->output]);
	}
	fprintf(test, " ");
	for (i = 0; i < nopo; i++)
	{
		fprintf(test, "%s", Dlevel_to_string[g_net[g_PrimaryOut[i]]->output]);
	}
	fprintf(test, "\n");
}

